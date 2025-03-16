# RESX Localization Tool

If  you ever had to translate strings scattered in multiple files, you would know what a hassle it can be, and this tool aims to help with that. It can:

1. **Export** all strings from RESX files to CSV. You just specify a folder, and it gets all resx files in all subfolders, and exports them to a csv.
2. **Translate** the strings using popular translation services
3. **Import** the translated strings back to their original RESX files, using the csv from the previous step.

- 📤 Exports strings to CSV with file paths, keys, values, and comments
- 🌐 Supports translation via multiple APIs:
  - Google Cloud Translation
  - DeepL (free and pro)
  - OpenAI API
- ⏸️ Resume capability for interrupted translations
- 🔄 Maintains XML structure and attributes of RESX files

## Installation

### Prerequisites

- Python 3.7+
- Required Python packages:
  - requests

### Setup

1. Clone this repository or download the script:

```bash
git clone https://github.com/istinmth/resx-localizer.git
cd resx-localization-tool
```

2. Install required dependencies:

```bash
pip install requests
```

3. Make the script executable (Linux/macOS):

```bash
chmod +x resx_tool.py
```

## Basic Usage

### Exporting Strings from RESX Files

Scan a folder and its subfolders for RESX files and export all strings to a CSV file:

```bash
python resx_tool.py export /path/to/project/folder exported_strings.csv
```

Add the `-v` flag for verbose logging:

```bash
python resx_tool.py export /path/to/project/folder exported_strings.csv -v
```

### Translating Strings

Translate the strings using one of the supported translation services:

#### Using DeepL:

```bash
python resx_tool.py translate exported_strings.csv translated_strings.csv --source en --target es --api deepl --key YOUR_DEEPL_API_KEY --delay 15
```

#### Using Google Cloud Translation:

```bash
python resx_tool.py translate exported_strings.csv translated_strings.csv --source en --target es --api google --key YOUR_GOOGLE_API_KEY
```

#### Using OpenAI:

```bash
python resx_tool.py translate exported_strings.csv translated_strings.csv --source English --target Spanish --api openai --key YOUR_OPENAI_API_KEY
```

### Importing Translated Strings

Import the translated strings back to their original RESX files:

```bash
python resx_tool.py import translated_strings.csv
```

## Advanced Usage

### Handling Rate Limits

When using translation APIs, you may encounter rate limits. The tool includes several features to help manage this:

1. **Adjust delay between requests**:

```bash
python resx_tool.py translate exported.csv translated.csv --source en --target es --api deepl --key YOUR_KEY --delay 15
```

The `--delay` parameter (in seconds) controls the time between translation requests. For DeepL free tier, a delay of 15-20 seconds is recommended.

2. **Reduce batch size**:

```bash
python resx_tool.py translate exported.csv translated.csv --source en --target es --api deepl --key YOUR_KEY --batch-size 1
```

Setting `--batch-size` to 1 processes one string at a time, which is safest for avoiding rate limits.

3. **Resume interrupted translations**:

If your translation process was interrupted, you can resume from a specific position:

```bash
python resx_tool.py translate exported.csv translated.csv --source en --target es --api deepl --key YOUR_KEY --start-at 50
```

This will skip the first 50 strings (assuming they've already been translated).

### Handling Empty Strings

The tool automatically handles empty strings by:

1. Detecting empty values in the source files
2. Creating appropriate placeholders based on the resource key name
3. Translating the placeholder content
4. Preserving the original formatting

## Troubleshooting

### "No .resx files found"
- Check that you're pointing to the correct directory
- Verify that the files have `.resx` extension (case-sensitive on some systems)
- Use the `-v` flag for verbose logging to see what's being scanned

### "Too Many Requests" / Rate Limit Errors
1. Increase the `--delay` parameter
2. Reduce the `--batch-size` to 1
3. Consider upgrading to a paid API plan for production use
4. Try a different translation service
5. Use `--start-at` to resume after cooling down

### File Encoding Issues
- The tool uses UTF-8 encoding by default
- Ensure your RESX files are properly formatted XML

### XML Parse Errors
- Check if the RESX files follow standard format
- Look for malformed XML tags or special characters

## License

This project is licensed under the MIT License - see the LICENSE file for details.
