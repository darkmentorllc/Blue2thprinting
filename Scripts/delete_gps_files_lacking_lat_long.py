
##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2024
##########################################

import os
import sys

def main():
    # Check if the directory path is provided as a command line argument
    if len(sys.argv) < 2:
        print("Usage: python3 delete_gps_files_lacking_lat_long.py directory_path")
        return

    directory_path = sys.argv[1]

    if not os.path.isdir(directory_path):
        print("Invalid directory path.")
        return

    # Loop through each file in the directory
    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        
        # Check if the file is a .txt file
        if os.path.isfile(file_path) and filename.endswith(".txt"):
            with open(file_path, 'r') as file:
                content = file.read()
                
                # Check if the content contains the specified string
                if ',"lat":' not in content:
                    os.remove(file_path)
                    print(f"Deleted file: {file_path}")

if __name__ == "__main__":
    main()
