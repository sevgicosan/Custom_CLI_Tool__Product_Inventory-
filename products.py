#!/usr/bin/env python3
"""Command-line tool for managing a small store's product inventory.

Data is stored in a UTF-8 JSON file with a next_id counter and a products
array, for example:

    {"next_id": 2, "products": [{"id": 1, "name": "Notebook", "price": "4.50", "quantity": 10}]}

Usage:
    python3 products.py [--file PATH] COMMAND [OPTIONS]

Commands: add, list, get, update, delete, low-stock, reorder.
Run "python3 products.py COMMAND --help" for command-specific help.
"""

import argparse
import json
import os
import re
import sys
import tempfile

PROG = "products.py"
DEFAULT_FILE = "products.json"

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

INPUT_PRICE_RE = re.compile(r"\d+(\.\d{1,2})?")
STORED_PRICE_RE = re.compile(r"\d+\.\d{2}")
NONNEGATIVE_INT_RE = re.compile(r"\d+")
NONWHITESPACE_RE = re.compile(r"\S")

PRODUCT_KEYS = {"id", "name", "price", "quantity"}
STORE_KEYS = {"next_id", "products"}


class ToolError(Exception):
    def __init__(self, message, exit_code=EXIT_FAILURE):
        super().__init__(message)
        self.exit_code = exit_code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(EXIT_USAGE, f"{self.prog}: error code {EXIT_USAGE}: {message}\n")


def validate_name(raw, flag="--name"):
    name = raw.strip()
    if not name:
        raise ToolError(
            f"invalid {flag}: name must contain at least one non-whitespace character",
            EXIT_USAGE,
        )
    return name


def validate_price(raw, flag="--price"):
    if not INPUT_PRICE_RE.fullmatch(raw):
        raise ToolError(
            f"invalid {flag} {raw!r}: expected a nonnegative amount with at most"
            " two decimal places (examples: 0, 4.5, 4.50)",
            EXIT_USAGE,
        )
    whole, _, fraction = raw.partition(".")
    return f"{whole}.{(fraction + '00')[:2]}"


def validate_nonnegative_integer(raw, flag):
    if not NONNEGATIVE_INT_RE.fullmatch(raw):
        raise ToolError(
            f"invalid {flag} {raw!r}: expected a nonnegative integer",
            EXIT_USAGE,
        )
    return int(raw)


def validate_id(raw):
    value = validate_nonnegative_integer(raw, "ID")
    if value < 1:
        raise ToolError(
            f"invalid ID {raw!r}: expected a positive integer",
            EXIT_USAGE,
        )
    return value


def validate_store(data, path):
    def invalid(reason):
        raise ToolError(f"data file {path} contains invalid store data: {reason}", EXIT_FAILURE)

    if not isinstance(data, dict):
        invalid("top-level value must be a JSON object")
    if set(data.keys()) != STORE_KEYS:
        invalid('expected an object with exactly the keys "next_id" and "products"')
    next_id = data["next_id"]
    if isinstance(next_id, bool) or not isinstance(next_id, int) or next_id < 1:
        invalid('"next_id" must be a positive integer')
    products = data["products"]
    if not isinstance(products, list):
        invalid('"products" must be a JSON array')
    seen_ids = set()
    for entry in products:
        if not isinstance(entry, dict):
            invalid("every product must be a JSON object")
        if set(entry.keys()) != PRODUCT_KEYS:
            invalid("every product must have exactly the keys id, name, price, and quantity")
        product_id = entry["id"]
        if isinstance(product_id, bool) or not isinstance(product_id, int) or product_id < 1:
            invalid("product id must be a positive integer")
        if product_id in seen_ids:
            invalid(f"product id {product_id} is duplicated")
        seen_ids.add(product_id)
        name = entry["name"]
        if not isinstance(name, str) or not NONWHITESPACE_RE.search(name):
            invalid("product name must be text with at least one non-whitespace character")
        price = entry["price"]
        if not isinstance(price, str) or not STORED_PRICE_RE.fullmatch(price):
            invalid('product price must be a string with exactly two decimal places (e.g., "4.50")')
        quantity = entry["quantity"]
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            invalid("product quantity must be a nonnegative integer")
    if products and next_id <= max(seen_ids):
        invalid('"next_id" must be greater than every existing product id')


def load_store(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except FileNotFoundError:
        return {"next_id": 1, "products": []}
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"cannot read data file {path}: {exc}", EXIT_FAILURE)
    if not text.strip():
        raise ToolError(f"data file {path} is empty; expected store data", EXIT_FAILURE)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolError(f"data file {path} is not valid JSON: {exc}", EXIT_FAILURE)
    validate_store(data, path)
    return data


def save_store(path, store):
    payload = json.dumps(store, indent=2, ensure_ascii=False) + "\n"
    directory = os.path.dirname(path) or "."
    try:
        handle, temp_path = tempfile.mkstemp(prefix=".products-", suffix=".tmp", dir=directory)
    except OSError as exc:
        raise ToolError(f"cannot write data file {path}: {exc}", EXIT_FAILURE)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(payload)
        os.replace(temp_path, path)
    except OSError as exc:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise ToolError(f"cannot write data file {path}: {exc}", EXIT_FAILURE)


def find_product(products, product_id):
    for product in products:
        if product["id"] == product_id:
            return product
    return None


def product_view(product):
    return {
        "id": product["id"],
        "name": product["name"],
        "price": product["price"],
        "quantity": product["quantity"],
    }


def not_found(product_id):
    return ToolError(f"product with ID {product_id} not found", EXIT_FAILURE)


def cmd_add(args):
    name = validate_name(args.name)
    price = validate_price(args.price)
    quantity = validate_nonnegative_integer(args.quantity, "--quantity")
    store = load_store(args.file)
    product = {
        "id": store["next_id"],
        "name": name,
        "price": price,
        "quantity": quantity,
    }
    store["products"].append(product)
    store["next_id"] += 1
    save_store(args.file, store)
    return product_view(product)


def cmd_list(args):
    store = load_store(args.file)
    products = sorted(store["products"], key=lambda product: product["id"])
    return [product_view(product) for product in products]


def cmd_get(args):
    product_id = validate_id(args.id)
    store = load_store(args.file)
    product = find_product(store["products"], product_id)
    if product is None:
        raise not_found(product_id)
    return product_view(product)


def cmd_update(args):
    product_id = validate_id(args.id)
    changes = {}
    if args.name is not None:
        changes["name"] = validate_name(args.name)
    if args.price is not None:
        changes["price"] = validate_price(args.price)
    if args.quantity is not None:
        changes["quantity"] = validate_nonnegative_integer(args.quantity, "--quantity")
    if not changes:
        raise ToolError(
            "update requires at least one of --name, --price, or --quantity",
            EXIT_USAGE,
        )
    store = load_store(args.file)
    product = find_product(store["products"], product_id)
    if product is None:
        raise not_found(product_id)
    product.update(changes)
    save_store(args.file, store)
    return product_view(product)


def cmd_delete(args):
    product_id = validate_id(args.id)
    store = load_store(args.file)
    product = find_product(store["products"], product_id)
    if product is None:
        raise not_found(product_id)
    store["products"].remove(product)
    save_store(args.file, store)
    return {"deleted_id": product_id}


def cmd_low_stock(args):
    threshold = validate_nonnegative_integer(args.threshold, "--threshold")
    store = load_store(args.file)
    matches = [product for product in store["products"] if product["quantity"] <= threshold]
    matches.sort(key=lambda product: product["id"])
    return [product_view(product) for product in matches]


def cmd_reorder(args):
    minimum = validate_nonnegative_integer(args.minimum, "--minimum")
    target = validate_nonnegative_integer(args.target, "--target")
    if target <= minimum:
        raise ToolError(
            f"--target {target} must be greater than --minimum {minimum}",
            EXIT_USAGE,
        )
    store = load_store(args.file)
    plan = []
    for product in sorted(store["products"], key=lambda item: item["id"]):
        if product["quantity"] <= minimum:
            plan.append(
                {
                    "id": product["id"],
                    "name": product["name"],
                    "current_quantity": product["quantity"],
                    "reorder_quantity": target - product["quantity"],
                }
            )
    return plan


def add_field_arguments(parser):
    parser.add_argument(
        "--name",
        metavar="NAME",
        help="product name, trimmed; at least one non-whitespace character",
    )
    parser.add_argument(
        "--price",
        metavar="PRICE",
        help='nonnegative amount with at most two decimal places, stored as "4.50"',
    )
    parser.add_argument(
        "--quantity",
        metavar="QTY",
        help="nonnegative integer",
    )


def build_parser():
    parser = Parser(
        prog=PROG,
        description="Manage a small store's product inventory in a JSON file.",
        epilog='Example: python3 products.py --file demo.json add --name "Notebook" --price 4.50 --quantity 10',
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        default=DEFAULT_FILE,
        help=f"path to the JSON data file, placed before the command (default: {DEFAULT_FILE})",
    )
    commands = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        required=True,
        title="commands",
    )

    add = commands.add_parser(
        "add",
        help="create one product and print it as a JSON object",
        description="Create one product, assign the next id, save it, and print it as a JSON object.",
    )
    add.add_argument("--name", required=True, metavar="NAME", help="product name, trimmed; at least one non-whitespace character")
    add.add_argument("--price", required=True, metavar="PRICE", help='nonnegative amount with at most two decimal places, stored as "4.50"')
    add.add_argument("--quantity", required=True, metavar="QTY", help="nonnegative integer")
    add.set_defaults(handler=cmd_add)

    list_parser = commands.add_parser(
        "list",
        help="print all products as a JSON array sorted by id",
        description="Print all products as a JSON array sorted by id ascending.",
    )
    list_parser.set_defaults(handler=cmd_list)

    get = commands.add_parser(
        "get",
        help="print one product as a JSON object",
        description="Print one product as a JSON object.",
    )
    get.add_argument("id", metavar="ID", help="positive integer product id")
    get.set_defaults(handler=cmd_get)

    update = commands.add_parser(
        "update",
        help="change fields of one product and print it",
        description="Update one or more fields of a product, save it, and print it as a JSON object. Requires at least one field flag; the id never changes.",
    )
    update.add_argument("id", metavar="ID", help="positive integer product id")
    add_field_arguments(update)
    update.set_defaults(handler=cmd_update)

    delete = commands.add_parser(
        "delete",
        help="delete one product",
        description='Delete one product and print {"deleted_id": ID}.',
    )
    delete.add_argument("id", metavar="ID", help="positive integer product id")
    delete.add_argument("--yes", action="store_true", required=True, help="confirm deletion without a prompt")
    delete.set_defaults(handler=cmd_delete)

    low_stock = commands.add_parser(
        "low-stock",
        help="list products at or below a quantity threshold",
        description="Print a JSON array of complete product objects whose quantity is at or below the threshold, sorted by id ascending. Read-only: never creates or modifies the data file.",
    )
    low_stock.add_argument("--threshold", required=True, metavar="QTY", help="nonnegative integer quantity threshold")
    low_stock.set_defaults(handler=cmd_low_stock)

    reorder = commands.add_parser(
        "reorder",
        help="plan reorder quantities for products at or below a minimum",
        description="Print a JSON array of objects for products whose quantity is at or below --minimum, each with reorder_quantity = --target - quantity, sorted by id ascending. Read-only: never creates or modifies the data file.",
    )
    reorder.add_argument("--minimum", required=True, metavar="MIN", help="nonnegative integer minimum quantity")
    reorder.add_argument("--target", required=True, metavar="TARGET", help="nonnegative integer target quantity, greater than MIN")
    reorder.set_defaults(handler=cmd_reorder)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except ToolError as error:
        print(f"{PROG}: error code {error.exit_code}: {error}", file=sys.stderr)
        return error.exit_code
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())
