from src.helper_functions import *
import bagit
import time
import subprocess
import sqlite3
import hashlib
import sys

logger = logging.getLogger(__name__)

TRANSFER_DIR = os.getenv("TRANSFER_DIR")
ARCHIVE_DIR = os.getenv("ARCHIVE_DIR")
LOGGING_DIR = os.getenv("LOGGING_DIR")
DATABASE = os.getenv("DATABASE")


def configure_db(database_connection):
    con = database_connection
    cur = con.cursor()
    try:
        cur.execute(
            "CREATE TABLE Collections(InternalSenderID PRIMARY KEY, Count INT DEFAULT 1)"
        )
    except sqlite3.OperationalError as e:
        logger.debug(f"Error creating table collections: {e}")
    try:
        cur.execute(
            "CREATE TABLE Transfers(TransferID INTEGER PRIMARY KEY AUTOINCREMENT, InternalSenderID, BagUUID, TransferDate, PayloadOxum, ManifestSHA256Hash, TransferTimeSeconds)"
        )
    except sqlite3.OperationalError as e:
        logger.debug(f"Error creating table transfers: {e}")
    cur.close()


def get_count_collections_processed(primary_id, db_connection):
    con = db_connection
    cur = con.cursor()
    res = cur.execute(
        "SELECT * FROM collections WHERE InternalSenderID=:id", {"id": primary_id}
    )
    results = res.fetchall()
    if len(results) == 0:
        return 0
    if len(results) > 1:
        raise ValueError(
            "Database configuration error - only one identifier entry should exist."
        )
    else:
        return results[0][1]


def is_processed(id, db_connection):
    count = get_count_collections_processed(id, db_connection)
    if count == 0:
        return False
    else:
        return True


def validate_dirs(dir_list):
    valid = True
    for dir in dir_list:
        if not os.path.exists(dir):
            valid = False
            logger.error(f"Directory does not exist: {dir}")
    return valid


def timed_rsync_copy(folder, output_dir):
    start = time.perf_counter()
    subprocess.run(["rsync", "-vrlt", f"{folder}/", output_dir])
    return time.perf_counter() - start


def main():
    valid_transfers = []
    valid_metadata = {}

    logfilename = f"{time.strftime('%Y%m%d')}_stash-it_transfer.log"
    logfile = os.path.join(LOGGING_DIR, logfilename)
    logging.basicConfig(
        filename=logfile,
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # check that directories are connected.
    if not validate_dirs([LOGGING_DIR, TRANSFER_DIR, ARCHIVE_DIR]):
        sys.exit()

    # Get the .ok files at the transfer directory
    at_transfer = os.listdir(TRANSFER_DIR)
    ok_files = [x for x in at_transfer if x.endswith(".ok")]

    if len(ok_files) == 0:
        logger.info("No trigger files staged in transfer directory.")
        sys.exit()
    else:
        logger.info(f"Transfers to process: {len(ok_files)}")
        for file in ok_files:
            tf = TriggerFile(os.path.join(TRANSFER_DIR, file))
            folder = tf.get_directory()
            if tf.validate():
                valid_transfers.append(folder)
                valid_metadata.update({folder: tf.get_metadata()})

    mc = MetadataChecker()

    # set up database
    database = DATABASE
    con = sqlite3.connect(database)
    configure_db(con)
    cur = con.cursor()

    for folder in valid_transfers:
        # generate and add a random uuid as External-Identifier
        metadata = valid_metadata.get(folder)
        metadata = mc.validate(metadata)
        if metadata is not None:
            # try to parse as bag and if that fails build new bag.
            try:
                bag = bagit.Bag(folder)
                logger.info(f"Processing existing bag at: {folder}")
                for key in metadata.keys():
                    bag.info[key] = metadata.get(key)
                bag.save()
            except Exception as e:
                logger.info(f"Making new bag at: {folder}")
                bag = bagit.make_bag(folder, bag_info=metadata)

            # check if bag is valid before moving.
            if bag.is_valid():
                # Hash manifest for dedupe
                manifest_hash = hashlib.sha256(
                    open(os.path.join(folder, "manifest-sha256.txt"), "rb").read()
                ).hexdigest()

                # check the transfer is unique
                results = cur.execute(
                    "SELECT * FROM transfers WHERE ManifestSHA256Hash=:id",
                    {"id": manifest_hash},
                )
                identical_folders = results.fetchall()
                if len(identical_folders) > 0:
                    raise ValueError(
                        f"Manifest hash conflict: folder {folder} with transaction id {identical_folders[0][0]} and folder title {identical_folders[0][1]}"
                    )

                # Check output directory
                count = get_count_collections_processed(folder, con)
                count += 1
                # Copy to output directory
                output_folder = os.path.join(
                    os.path.basename(os.path.normpath(folder)), f"t{count}"
                )
                output_dir = os.path.join(ARCHIVE_DIR, output_folder)

                if not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                copy_time = timed_rsync_copy(folder, output_dir)

            output_bag = bagit.Bag(output_dir)

            # check copied bag is valid and if so update database
            if output_bag.is_valid():
                cur.execute(
                    "INSERT INTO collections(InternalSenderID) VALUES(:id) ON CONFLICT (InternalSenderID) DO UPDATE SET count = count + 1",
                    {"id": folder},
                )
                con.commit()
                cur.execute(
                    "INSERT INTO transfers(InternalSenderID, BagUUID, TransferDate, PayloadOxum, ManifestSHA256Hash,TransferTimeSeconds) VALUES(:InternalSenderId, :BagUUID, :TransferDate, :PayloadOxum, :ManifestSHA, :TransferTime)",
                    {
                        "InternalSenderId": folder,
                        "BagUUID": bag.info[
                            "External-Description"
                        ],  # fix this so it only includes the UUID
                        "TransferDate": time.strftime("%Y%m%d"),
                        "PayloadOxum": bag.info["Payload-Oxum"],
                        "ManifestSHA": manifest_hash,
                        "TransferTime": copy_time,
                    },
                )
                con.commit()
        else:
            logger.error(f"Error moving bag: {e}")


main()
