import xml.etree.ElementTree as ET
import argparse

# Define a function to recursively process XML elements
def process_element(element, indent=0):
    attribute_id = element.get('id')
    tag = element.tag
    value = element.find('*[@value]')
    
    if value is not None:
        value = value.get('value')
    
    # Create indentation for pretty printing
    indentation = '  ' * indent
    
    print(f"{indentation}Attribute ID: {attribute_id}, Tag: {tag}, Value: {value}")
    
    # Process child elements recursively
    for child in element:
        process_element(child, indent + 1)

def main():
    # Create a command-line argument parser
    parser = argparse.ArgumentParser(description='Parse and display information in XML records.')
    parser.add_argument('xml_file', type=str, help='Path to the XML file to parse')

    # Parse the command-line arguments
    args = parser.parse_args()

    try:
        with open(args.xml_file, 'r') as file:
            xml_data = file.read()
        
        # Split the input XML into separate records
        records = xml_data.split('<?xml version="1.0" encoding="UTF-8" ?>')
        
        # Skip the first element (empty string before the first record)
        for record in records[1:]:
            # Reconstruct a valid XML record by adding the missing XML declaration
            record = '<?xml version="1.0" encoding="UTF-8" ?>\n<record>\n' + record
            
            # Parse the XML record
            tree = ET.ElementTree(ET.fromstring(record))
            root = tree.getroot()
            
            # Process the root element
            process_element(root)
            
    except FileNotFoundError:
        print(f"Error: The file '{args.xml_file}' does not exist.")
    except ET.ParseError:
        print(f"Error: Unable to parse the XML file '{args.xml_file}'.")

if __name__ == '__main__':
    main()
