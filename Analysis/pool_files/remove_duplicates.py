import os
import re
import datetime
import hashlib

def find_and_delete_duplicate_files(directory="."):
    """
    Finds files with duplicate content (based on SHA1 hash prefix) in a directory,
    keeps the file with the earliest timestamp, and deletes the rest.

    Args:
        directory: The directory to search in (defaults to the current directory).
    """

    file_data = {}  # Dictionary to store file information {hash: [(timestamp, filename), ...]}

    for filename in os.listdir(directory):
        match = re.match(r"([0-9a-f]{40})-(.+)-(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.json\.processed", filename)
        if match:
            sha1_hash, _, timestamp_str = match.groups()
            try:
                timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d-%H-%M-%S")
            except ValueError:
                print(f"Warning: Could not parse timestamp from filename: {filename}. Skipping.")
                continue

            if sha1_hash not in file_data:
                file_data[sha1_hash] = []
            file_data[sha1_hash].append((timestamp, filename))

    for sha1_hash, files in file_data.items():
        if len(files) > 1:  # If there are duplicates
            files.sort()  # Sort by timestamp (earliest first)
            earliest_file = files[0][1]
            print(f"Found duplicate files for hash: {sha1_hash}")
            print(f"Keeping: {earliest_file}")
            for timestamp, filename in files[1:]:  # Iterate through duplicates (excluding the first)
                print(f"Deleting: {filename}")
                try:
                    os.remove(os.path.join(directory, filename))
                except OSError as e:
                    print(f"Error deleting file {filename}: {e}")
        elif len(files) == 1:
            print(f"Found single file for hash: {sha1_hash}")
            print(f"Keeping: {files[0][1]}")
        else:
            print(f"No files found for hash: {sha1_hash}")


if __name__ == "__main__":
    find_and_delete_duplicate_files()
