# stash-it

## Overview

This is a basic workflow for stashing data safely on a server with minimum metadata as BagIt bags. Includes a record of transfers using a sqlite3 database.

## Getting started

### Dependencies

- [bagit](https://github.com/LibraryOfCongress/bagit-python)
- [Pytest](https://docs.pytest.org/en/stable/)

### Staging script

This process is designed to use minimal metadata submitted as JSON. The current configuration looks for a `folder_title.ok` file that contains minimum metadata. 

To generate these files, a Windows Batch file can be created to generate a `folder_title.ready` file with minimum metadata fields. Once the metadata is updated, the user renames the file to `.ok`.

Example `.bat` script:

        @echo off
        for /D %%i in (*) do if not exist %%i.ok (
            if not exist %%i.error (
                set var=%%i
                call :metadata %var% >%%i.ready))

        :metadata
        echo {"Source-Organization":"",
        echo "Contact-Name":"",
        echo "External-Description":"",
        echo "Internal-Sender-Identifier": "%var%"}

### Trigger file handling

Required metadata fields are configured in the `.env` file. See `env.example` for example fields. Additional fields can be included, but expects at least these.

The `TriggerFile` class expects a `.ok` file submitted as a path. It performs basic validation checks:
- Does the folder exist?
- Does it have data in it?
- Was metadata included in the staging file?
- Does it have the right keys?
- Are all the values set?

Any failing conditions are tracked and the errors written to a `.error` file along with a default metadata form.

#### Existing bags

Existing bags can be processed with the trigger file. To use the `.ok` file metadata, delete the `bag-info.txt` file. Otherwise it will use the bag metadata.

### Adding UUIDs

A UUID is added to each bag in `External-Identifier` field. The `MetadataChecker` class looks for existing UUIDs and will only add one if one is not already parsed.

### Copying to output directory

Copying is handled in the runner script (`stash_it.py`) using [rsync](https://linux.die.net/man/1/rsync) with the following flags `-vrlt`.

A sqlite3 database is used to store a record of collections (folders) and transactions (transfers). To check for duplicate data transfers, the hash of the SHA256 manifest is added to the transactions and checked before moving data. 

In the output location, files are stored in the transfer folder they were submitted from, within a subfolder t1 that increments as transfers are added.

### Metadata model

To do:
- Outline the model

### Testing

Some tests have been created for:
- `TriggerFile` class
- `MetadataChecker` class

## Development

To do:
- Collection profiling on transfer (file ext only)
- Validation script with logging/db
- Integration with Obsidian for cataloguing
- Granular deduplication and `fetch.txt` integration