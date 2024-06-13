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
        if child.tag == 'sequence':
            process_sequence(child, indent + 1)
        else:
            process_element(child, indent + 1)

def process_sequence(sequence_element, indent):
    indentation = '  ' * indent

    sequence_values = []
    for seq_item in sequence_element:
        if seq_item.tag == 'uint16' or seq_item.tag == 'uuid' or seq_item.tag == 'uint8':
            value = seq_item.get('value')
            sequence_values.append(value)

    if sequence_values:
        print(f"{indentation}Sequence Values: {', '.join(sequence_values)}")

def main():
    # Create a command-line argument parser
    parser = argparse.ArgumentParser(description='Parse and display information in XML records.')
    parser.add_argument('xml_file', type=str, help='Path to the XML file to parse')

    # Parse the command-line arguments
    args = parser.parse_args()

    try:
        with open(args.xml_file, 'r') as file:
            in_record = False
            record = ""

            for line in file:
                if line.strip() == "<record>":
                    in_record = True
                    record = line
                elif line.strip() == "</record>":
                    in_record = False
                    record += line
                    # Parse the XML record
                    tree = ET.ElementTree(ET.fromstring(record))
                    root = tree.getroot()

                    # Process the root element
                    process_element(root)
                elif in_record:
                    record += line

    except FileNotFoundError:
        print(f"Error: The file '{args.xml_file}' does not exist.")
    except ET.ParseError:
        print(f"Error: Unable to parse the XML file '{args.xml_file}'.")

if __name__ == '__main__':
    main()
