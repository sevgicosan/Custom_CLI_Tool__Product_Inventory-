# Product Inventory CLI Tool

## Project Overview


This project is a Python 3 command-line tool for managing a small store's product inventory. It was developed with assistance from the ViberCode Coding Agent.


The tool lets users add, list, retrieve, update, and delete products stored in a local JSON file. It also includes two custom commands: **Low-Stock Report** and **Reorder Planning**.


The project is intended both for people learning how to build custom Python CLI commands and for small-store owners who want a simple way to check stock levels and plan replenishment.


## Requirements


- Python 3
- No third-party packages required to run the tool


Open Terminal in the folder containing `products.py` and run commands using:


```bash
python3 products.py [--file PATH] COMMAND [OPTIONS]
```


The optional `--file PATH` argument must come **before** the command. If omitted, the tool uses `products.json` in the current working directory. Square brackets in the syntax indicate optional arguments; do not type them literally.


## Available Commands


| Command | Description |
|---|---|
| `add` | Add a new product with its name, price, and quantity. |
| `list` | Display all products, sorted by their IDs. |
| `get` | Retrieve a specific product using its ID. |
| `update` | Change an existing product's name, price, or quantity. |
| `delete` | Remove a product using its ID and the `--yes` confirmation flag. |
| `low-stock` | Find products with quantities **less than or equal to** a chosen threshold. For example, a threshold of 5 returns products with 5 or fewer units. |
| `reorder` | Find products at or below a chosen minimum quantity and calculate how many more units are needed to reach a target. For example, with a minimum of 5, target of 20, and 3 units in stock, it recommends ordering 17 units. |


For general help, run:


```bash
python3 products.py --help
```


For help on an individual command, use a command such as `python3 products.py reorder --help`.


## Basic Inventory Commands


```bash
# Add a product
python3 products.py add --name "Notebook" --price 4.5 --quantity 10


# List all products
python3 products.py list


# Get product with ID 1
python3 products.py get 1


# Update its quantity
python3 products.py update 1 --quantity 12


# Delete it (confirmation is required)
python3 products.py delete 1 --yes
```


Each product has an automatically assigned ID, a name, a price stored as a string with two decimal places, and a nonnegative integer quantity. IDs start at 1 and are never reused after deletion.


## Custom Feature 1: Low-Stock Report


### Purpose and users


Low-Stock Report helps store owners and inventory managers quickly identify products that may need restocking. It also demonstrates how a custom CLI command can filter existing inventory data.


### Command syntax and input


```bash
python3 products.py low-stock --threshold QTY
```


- `--threshold QTY`: Required nonnegative integer. Products with a quantity **at or below** this value are included.


### Runnable example


To try this with a separate inventory file, start with a filename that does not already exist, such as `example_inventory.json`:


```bash
python3 products.py --file example_inventory.json add --name "Notebook" --price 4.50 --quantity 10
python3 products.py --file example_inventory.json add --name "Pencil" --price 1.25 --quantity 3
python3 products.py --file example_inventory.json low-stock --threshold 5
```


Expected output of the final command:


```json
[
  {
    "id": 2,
    "name": "Pencil",
    "price": "1.25",
    "quantity": 3
  }
]
```


Pencil is included because 3 is less than or equal to 5. Notebook is excluded because its quantity is 10. A product with exactly 5 units would also be included.


**Edge cases:** If nothing matches, the command returns `[]`. A missing, negative, or non-integer threshold produces an error. The command does not change inventory or create a missing data file.


## Custom Feature 2: Reorder Planning


### Purpose and users


Reorder Planning helps store owners and inventory managers identify products that need replenishment **and** calculate how many additional units would be needed to reach a target stock level. It makes a recommendation; it does not place orders or update product quantities.


### Command syntax and inputs


```bash
python3 products.py reorder --minimum MIN --target TARGET
```


- `--minimum MIN`: Required nonnegative integer. Products with quantities at or below this minimum qualify.
- `--target TARGET`: Required nonnegative integer for the desired stock level. It must be **greater than** `MIN`.


For each qualifying product:


```text
reorder_quantity = target - current_quantity
```


### Runnable example


Using the same `example_inventory.json` and the products added above:


```bash
python3 products.py --file example_inventory.json reorder --minimum 5 --target 20
```


Expected output:


```json
[
  {
    "id": 2,
    "name": "Pencil",
    "current_quantity": 3,
    "reorder_quantity": 17
  }
]
```


Pencil has 3 units, which is at or below the minimum of 5. The program recommends `20 - 3 = 17` additional units.


**Edge cases:** If no products qualify, the command returns `[]`. Missing or negative/non-integer arguments, or a target less than or equal to the minimum, produce an error. The command does not modify inventory or create a missing data file.


## Data Storage and File Selection


Inventory records are stored in a local JSON file. After the first successful add, the file may look like this:


```json
{
  "next_id": 2,
  "products": [
    {"id": 1, "name": "Notebook", "price": "4.50", "quantity": 10}
  ]
}
```


- `next_id` tracks the next product ID; deleting a product does not reset it.
- `products` contains the saved product records.
- Changes from successful `add`, `update`, and `delete` operations persist across separate command runs.
- Read-only commands (`list`, `get`, `low-stock`, and `reorder`) do not change the file.


Use a different inventory file by putting `--file` before the command:


```bash
python3 products.py --file demo.json list
python3 products.py --file demo.json low-stock --threshold 5
python3 products.py --file demo.json reorder --minimum 5 --target 20
```


If a selected file does not exist, read-only list and custom report commands return an empty JSON array, and the first successful add creates the new file.


## Validation and Error Handling


The tool rejects invalid product IDs, empty names, invalid prices, negative or fractional quantities, missing required arguments, and invalid custom-command inputs. A deletion requires `--yes` rather than an interactive confirmation.


Commands return exit code `0` for success, `1` for missing products or file/data errors, and `2` for invalid syntax or input. Failed operations do not modify stored inventory or consume a new product ID.


## Development and Testing


The project was developed using Python 3 and its standard libraries, including `argparse` for command-line argument handling and `json` for storage. ViberCode was used as the Coding Agent, and Git/GitHub is used for version control.


The included `test_products.py` can be run with:


```bash
python3 -m unittest test_products.py -v
```


The tool can also be tested by running the example commands above in Terminal.
