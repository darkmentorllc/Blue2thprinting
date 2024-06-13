#!/usr/bin/bash
FILES="$@"

LOGPATH='/home/user/Blue2thprinting/Scripts/logs/btmon'

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
