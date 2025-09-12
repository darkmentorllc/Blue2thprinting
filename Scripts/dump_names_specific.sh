#!/usr/bin/bash

##########################################
# Created by Xeno Kovah
# Copyright(c) © Dark Mentor LLC 2023-2026
##########################################

FILES="$@"

LOGPATH='/home/user/Blue2thprinting/Logs/btmon'

rm ~/names.txt

for pattern in "$@"
do
	find "$LOGPATH" -name "$pattern" -print0 | while IFS= read -r -d '' file
        do
		echo "Processing " ${file}

		echo "btmon -T -r $file.bin | grep -e \"Name (.*):\" | sort | uniq"
		btmon -T -r $file | grep -e "Name (.*):" | sort | uniq >> ~/names.txt
	done
done

echo "All found names:"
cat ~/names.txt | sort | uniq
