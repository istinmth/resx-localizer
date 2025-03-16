#!/usr/bin/env python3
import os
import csv
import argparse
import xml.etree.ElementTree as ET
from xml.dom import minidom
import logging
from typing import Dict, List, Tuple
import sys
import requests
import json
import time
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def find_resx_files(root_folder: str) -> List[str]:
    """
    Recursively find all .resx files in the given folder and its subfolders.

    Args:
        root_folder: The root folder to start searching from

    Returns:
        A list of paths to .resx files
    """
    resx_files = []
    logger.info(f"Scanning {root_folder} for .resx files...")

    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.lower().endswith('.resx'):
                resx_files.append(os.path.join(dirpath, filename))

    logger.info(f"Found {len(resx_files)} .resx files")
    return resx_files

def extract_strings_from_resx(resx_file: str) -> List[Dict[str, str]]:
    """
    Extract string resources from a .resx file.

    Args:
        resx_file: Path to the .resx file

    Returns:
        A list of dictionaries containing the string data
    """
    try:
        tree = ET.parse(resx_file)
        root = tree.getroot()

        # Try different namespace approaches
        namespaces = [
            {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'},
            {}  # Empty namespace for standard RESX files
        ]

        # Extract the default namespace if it exists
        if root.tag.startswith('{'):
            ns = root.tag.split('}')[0].strip('{')
            namespaces.insert(0, {'ns': ns})

        # Try to find data elements with different namespace approaches
        data_elements = []
        for ns in namespaces:
            if not ns:  # Empty namespace
                elements = root.findall('.//data')
                if elements:
                    data_elements = elements
                    break
            else:
                elements = root.findall('.//ns:data', ns)
                if elements:
                    data_elements = elements
                    namespaces = [ns]  # Use this namespace for subsequent searches
                    break

        # If still no elements found, try direct xpath
        if not data_elements:
            data_elements = root.findall('./data')

        # Log the number of data elements found for debugging
        logger.debug(f"Found {len(data_elements)} data elements in {resx_file}")

        results = []
        for data_element in data_elements:
            name = data_element.get('name')
            if name is None:
                continue

            # Get value element
            value_element = None
            for ns in namespaces:
                if not ns:  # Empty namespace
                    value_element = data_element.find('./value')
                else:
                    value_element = data_element.find('./ns:value', ns)

                if value_element is not None:
                    break

            # If value element exists and has text (or empty text)
            if value_element is not None:
                # Get text or empty string
                value_text = value_element.text if value_element.text is not None else ""

                # Get comment element if it exists
                comment_element = None
                for ns in namespaces:
                    if not ns:  # Empty namespace
                        comment_element = data_element.find('./comment')
                    else:
                        comment_element = data_element.find('./ns:comment', ns)

                    if comment_element is not None:
                        break

                comment = ""
                if comment_element is not None and comment_element.text is not None:
                    comment = comment_element.text

                results.append({
                    'file': resx_file,
                    'key': name,
                    'value': value_text,
                    'comment': comment
                })

        logger.debug(f"Extracted {len(results)} strings from {resx_file}")
        return results
    except Exception as e:
        logger.error(f"Error extracting strings from {resx_file}: {str(e)}")
        return []

def export_to_csv(strings_data: List[Dict[str, str]], output_file: str) -> None:
    """
    Export the extracted string data to a CSV file.

    Args:
        strings_data: List of dictionaries containing string data
        output_file: Path to the output CSV file
    """
    try:
        fieldnames = ['file', 'key', 'value', 'comment']

        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(strings_data)

        logger.info(f"Exported {len(strings_data)} strings to {output_file}")
    except Exception as e:
        logger.error(f"Error exporting to CSV: {str(e)}")
        raise

def parse_csv(csv_file: str) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Parse the CSV file containing the modified strings.

    Args:
        csv_file: Path to the CSV file

    Returns:
        A nested dictionary mapping file -> key -> {value, comment}
    """
    result = {}

    try:
        with open(csv_file, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                file_path = row.get('file', '')
                key = row.get('key', '')
                value = row.get('value', '')
                comment = row.get('comment', '')

                if not file_path or not key:
                    continue

                if file_path not in result:
                    result[file_path] = {}

                result[file_path][key] = {
                    'value': value,
                    'comment': comment
                }

        logger.info(f"Parsed {sum(len(keys) for keys in result.values())} strings from {csv_file}")
        return result
    except Exception as e:
        logger.error(f"Error parsing CSV file: {str(e)}")
        raise

def update_resx_file(resx_file: str, string_data: Dict[str, Dict[str, str]]) -> None:
    """
    Update a .resx file with modified strings.

    Args:
        resx_file: Path to the .resx file
        string_data: Dictionary mapping key -> {value, comment}
    """
    try:
        # Parse the RESX file
        tree = ET.parse(resx_file)
        root = tree.getroot()

        # Try different namespace approaches
        namespaces = [
            {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'},
            {}  # Empty namespace for standard RESX files
        ]

        # Extract the default namespace if it exists
        if root.tag.startswith('{'):
            ns = root.tag.split('}')[0].strip('{')
            namespaces.insert(0, {'ns': ns})

        # Find all data elements
        data_elements = []
        active_namespace = None

        for ns in namespaces:
            if not ns:  # Empty namespace
                elements = root.findall('.//data')
            else:
                elements = root.findall('.//ns:data', ns)

            if elements:
                data_elements = elements
                active_namespace = ns
                break

        # If still no elements found, try direct xpath
        if not data_elements:
            data_elements = root.findall('./data')
            active_namespace = {}

        # Track changes
        changes_count = 0

        for data_element in data_elements:
            name = data_element.get('name')
            if name and name in string_data:
                # Get and update value element
                value_element = None

                if not active_namespace:  # Empty namespace
                    value_element = data_element.find('./value')
                else:
                    value_element = data_element.find('./ns:value', active_namespace)

                if value_element is not None:
                    old_value = value_element.text if value_element.text is not None else ""
                    new_value = string_data[name]['value']
                    if old_value != new_value:
                        value_element.text = new_value
                        changes_count += 1

                # Update comment if it exists
                comment = string_data[name]['comment']
                if comment:
                    comment_element = None

                    if not active_namespace:  # Empty namespace
                        comment_element = data_element.find('./comment')
                    else:
                        comment_element = data_element.find('./ns:comment', active_namespace)

                    # Create comment element if it doesn't exist
                    if comment_element is None:
                        if active_namespace and 'ns' in active_namespace:
                            ns_prefix = f"{{{active_namespace['ns']}}}" if active_namespace['ns'] else ""
                            comment_element = ET.SubElement(data_element, f"{ns_prefix}comment")
                        else:
                            comment_element = ET.SubElement(data_element, "comment")

                    old_comment = comment_element.text if comment_element.text is not None else ""
                    if old_comment != comment:
                        comment_element.text = comment
                        changes_count += 1

        # Write back to file with proper formatting
        xmlstr = ET.tostring(root, encoding='utf-8')
        parsed_xml = minidom.parseString(xmlstr)
        pretty_xml = parsed_xml.toprettyxml(indent="  ", encoding='utf-8')

        with open(resx_file, 'wb') as f:
            f.write(pretty_xml)

        logger.info(f"Updated {resx_file} with {changes_count} changes")
    except Exception as e:
        logger.error(f"Error updating RESX file {resx_file}: {str(e)}")
        raise

# Translation Methods

def translate_with_google(text, source_lang, target_lang, api_key):
    """
    Translate text using Google Cloud Translation API.

    Args:
        text: Text to translate
        source_lang: Source language code
        target_lang: Target language code
        api_key: Google Cloud API key

    Returns:
        Translated text
    """
    if not text.strip():
        return text

    url = f"https://translation.googleapis.com/language/translate/v2?key={api_key}"
    payload = {
        'q': text,
        'source': source_lang,
        'target': target_lang,
        'format': 'text'
    }

    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            result = response.json()
            return result['data']['translations'][0]['translatedText']
        else:
            logger.error(f"Translation API error: {response.status_code} - {response.text}")
            return text
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        return text

def translate_with_deepl(text, source_lang, target_lang, api_key):
    """
    Translate text using DeepL API.

    Args:
        text: Text to translate
        source_lang: Source language code
        target_lang: Target language code
        api_key: DeepL API key

    Returns:
        Translated text
    """
    if not text.strip():
        return text

    url = "https://api-free.deepl.com/v2/translate"
    headers = {
        "Authorization": f"DeepL-Auth-Key {api_key}"
    }
    payload = {
        "text": [text],
        "source_lang": source_lang.upper(),
        "target_lang": target_lang.upper(),
        "preserve_formatting": 1
    }

    try:
        response = requests.post(url, headers=headers, data=payload)
        if response.status_code == 200:
            result = response.json()
            return result['translations'][0]['text']
        else:
            logger.error(f"DeepL API error: {response.status_code} - {response.text}")
            return text
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        return text

def translate_with_openai(text, source_lang, target_lang, api_key):
    """
    Translate text using OpenAI API.

    Args:
        text: Text to translate
        source_lang: Source language name
        target_lang: Target language name
        api_key: OpenAI API key

    Returns:
        Translated text
    """
    if not text.strip():
        return text

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "system",
                "content": f"You are a professional translator. Translate the following text from {source_lang} to {target_lang}. Maintain the formatting. Only respond with the translation, no explanations or additional text."
            },
            {
                "role": "user",
                "content": text
            }
        ],
        "temperature": 0.3
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return text
    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        return text

def translate_csv(input_file, output_file, source_lang, target_lang, api_type, api_key, batch_size=3, delay=2, start_at=0):
    """
    Translate all strings in a CSV file.

    Args:
        input_file: Input CSV file
        output_file: Output CSV file
        source_lang: Source language code or name
        target_lang: Target language code or name
        api_type: 'google', 'deepl', or 'openai'
        api_key: API key for the selected service
        batch_size: Number of texts to translate in a batch (default: 3)
        delay: Delay between translations in seconds (default: 2)
        start_at: Start translating from this row index (default: 0)
    """
    try:
        # Read the input CSV
        rows = []
        with open(input_file, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            fieldnames = reader.fieldnames

            for row in reader:
                rows.append(row)

        # If starting from a specific row
        if start_at > 0:
            if start_at >= len(rows):
                logger.error(f"Start index {start_at} is out of range. File only has {len(rows)} rows.")
                return 1
            logger.info(f"Starting translation from row {start_at} (skipping {start_at} rows)")

            # If continuing from a previous run, read the existing output file
            if os.path.exists(output_file):
                translated_rows = []
                with open(output_file, 'r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for i, row in enumerate(reader):
                        if i < start_at:
                            translated_rows.append(row)

                # Replace the first 'start_at' rows with the translated ones
                if len(translated_rows) == start_at:
                    rows[:start_at] = translated_rows

        logger.info(f"Translating {len(rows)} strings from {source_lang} to {target_lang}...")

        # Select translation function
        if api_type == 'google':
            translate_func = lambda text: translate_with_google(text, source_lang, target_lang, api_key)
        elif api_type == 'deepl':
            translate_func = lambda text: translate_with_deepl(text, source_lang, target_lang, api_key)
        elif api_type == 'openai':
            translate_func = lambda text: translate_with_openai(text, source_lang, target_lang, api_key)
        else:
            logger.error(f"Unknown API type: {api_type}")
            return 1

        # Process in batches to avoid overloading the API
        total_batches = (len(rows) + batch_size - 1) // batch_size

        # Create an intermediate output file to save progress
        temp_output_file = f"{output_file}.temp"
        progress_counter = 0

        def translate_row(row):
            # If value is empty, create a placeholder for translation
            value = row['value']
            if not value.strip():
                # Look at the key to determine a reasonable placeholder
                key_parts = row['key'].split('.')
                if len(key_parts) > 1:
                    # Use the part before .Text or similar suffix as placeholder
                    placeholder = key_parts[0].replace('ph', '').replace('_', ' ').strip()
                    if placeholder:
                        value = f"[{placeholder}]"

            # Add retry logic to handle API rate limits
            max_retries = 3
            retry_delay = 5  # seconds

            for retry in range(max_retries):
                try:
                    translated_value = translate_func(value)

                    # Also translate comments if they exist
                    translated_comment = ""
                    if row['comment']:
                        # Add delay between value and comment translation
                        time.sleep(1)
                        translated_comment = translate_func(row['comment'])

                    row['value'] = translated_value
                    row['comment'] = translated_comment

                    # Success - return the row
                    return row
                except Exception as e:
                    if retry < max_retries - 1:
                        logger.warning(f"Translation failed for '{value}', retrying in {retry_delay} seconds... ({str(e)})")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error(f"Translation failed after {max_retries} attempts: {str(e)}")
                        # Return the original row if all retries fail
                        return row

        for i in range(total_batches):
            start_idx = i * batch_size
            end_idx = min(start_idx + batch_size, len(rows))
            batch = rows[start_idx:end_idx]

            logger.info(f"Translating batch {i+1}/{total_batches} ({start_idx+1}-{end_idx} of {len(rows)})...")

            # Process each item in the batch sequentially to avoid rate limits
            translated_batch = []
            for row in batch:
                logger.info(f"Translating: '{row['key']}' - '{row['value']}'")
                translated_row = translate_row(row)
                translated_batch.append(translated_row)
                progress_counter += 1

                # Save progress after each row
                all_rows = rows[:start_idx] + translated_batch + rows[start_idx + len(translated_batch):]
                with open(temp_output_file, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_rows)

                # Add a delay between each row to avoid rate limits
                time.sleep(delay)  # Configurable delay between individual items

            # Update rows with translated batch
            for j, translated_row in enumerate(translated_batch):
                rows[start_idx + j] = translated_row

            # Save progress after each batch
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            # Add a longer delay between batches
            if i < total_batches - 1:
                delay = 2  # 5 seconds between batches
                logger.info(f"Batch complete. Pausing for {delay} seconds before next batch...")
                time.sleep(delay)

        # Final save to the output file
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # Remove the temporary file
        if os.path.exists(temp_output_file):
            os.remove(temp_output_file)

        logger.info(f"Translation completed. Translated data saved to {output_file}")
        return 0

    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        return 1

def export_strings(args):
    """Export strings from RESX files to CSV"""
    if not os.path.isdir(args.folder):
        logger.error(f"Folder {args.folder} does not exist or is not a directory")
        return 1

    # Find all RESX files
    resx_files = find_resx_files(args.folder)
    if not resx_files:
        logger.warning(f"No .resx files found in {args.folder}")
        return 0

    # Extract strings from all files
    all_strings = []
    for resx_file in resx_files:
        strings = extract_strings_from_resx(resx_file)
        all_strings.extend(strings)

    if not all_strings:
        logger.warning("No strings found in any .resx files")
        return 0

    # Export to CSV
    export_to_csv(all_strings, args.output)
    logger.info(f"Successfully exported {len(all_strings)} strings to {args.output}")
    return 0

def import_strings(args):
    """Import strings from CSV and update RESX files"""
    if not os.path.isfile(args.csv):
        logger.error(f"CSV file {args.csv} does not exist")
        return 1

    # Parse CSV
    string_data = parse_csv(args.csv)
    if not string_data:
        logger.warning(f"No valid string data found in {args.csv}")
        return 0

    # Update RESX files
    success_count = 0
    error_count = 0

    for resx_file, keys in string_data.items():
        if not os.path.isfile(resx_file):
            logger.warning(f"RESX file {resx_file} does not exist, skipping")
            error_count += 1
            continue

        try:
            update_resx_file(resx_file, keys)
            success_count += 1
        except Exception as e:
            error_count += 1
            logger.error(f"Failed to update {resx_file}: {str(e)}")

    logger.info(f"Import completed: {success_count} files updated successfully, {error_count} files failed")
    return 0 if error_count == 0 else 1

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="RESX Localization Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export strings from RESX files to CSV")
    export_parser.add_argument("folder", help="Root folder to scan for RESX files")
    export_parser.add_argument("output", help="Output CSV file")
    export_parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import strings from CSV and update RESX files")
    import_parser.add_argument("csv", help="CSV file containing the strings to import")
    import_parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    # Translate command
    translate_parser = subparsers.add_parser("translate", help="Translate strings in CSV file")
    translate_parser.add_argument("input", help="Input CSV file")
    translate_parser.add_argument("output", help="Output CSV file")
    translate_parser.add_argument("--source", required=True, help="Source language code (e.g., 'en' for Google/DeepL or 'English' for OpenAI)")
    translate_parser.add_argument("--target", required=True, help="Target language code (e.g., 'es' for Google/DeepL or 'Spanish' for OpenAI)")
    translate_parser.add_argument("--api", choices=["google", "deepl", "openai"], required=True, help="Translation API to use")
    translate_parser.add_argument("--key", required=True, help="API key for the selected translation service")
    translate_parser.add_argument("--batch-size", type=int, default=3, help="Number of strings to translate in a batch (default: 3)")
    translate_parser.add_argument("--delay", type=int, default=2, help="Delay between translations in seconds (default: 2)")
    translate_parser.add_argument("--start-at", type=int, default=0, help="Start translating from this row index (default: 0)")
    translate_parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    if args.command == "export":
        return export_strings(args)
    elif args.command == "import":
        return import_strings(args)
    elif args.command == "translate":
        return translate_csv(args.input, args.output, args.source, args.target, args.api, args.key,
                            args.batch_size, args.delay, args.start_at)
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())