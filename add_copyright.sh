#!/bin/bash
copyright="\"\"\"\nCopyright (c) 2026 lingge66. All rights reserved.\nThis code is part of the Binance AI Agent project and is protected by copyright law.\nUnauthorized copying, modification, distribution, or use of this code is strictly prohibited.\n\"\"\"\n\n"

for file in $(find . -name "*.py"); do
    if ! grep -q "Copyright (c) 2026 lingge66" "$file"; then
        temp_file=$(mktemp)
        echo -e "$copyright" | cat - "$file" > "$temp_file"
        mv "$temp_file" "$file"
        echo "Added copyright to $file"
    fi
done
