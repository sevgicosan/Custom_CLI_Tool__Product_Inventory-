#!/usr/bin/env python3
"""Black-box test suite for products.py, driven by the CLI as a subprocess."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(REPO, "products.py")
PYTHON = sys.executable


def run_tool(argv, cwd=None):
    return subprocess.run(
        [PYTHON, TOOL, *argv],
        capture_output=True,
        text=True,
        cwd=cwd or REPO,
        timeout=30,
    )


def parse_json(stdout):
    return json.loads(stdout)


class TempFileCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "products.json")

    def tearDown(self):
        self.tmp.cleanup()

    def exists(self):
        return os.path.exists(self.data)

    def run_cli(self, argv):
        return run_tool(["--file", self.data, *argv])

    def contents(self):
        with open(self.data, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def write(self, text):
        with open(self.data, "w", encoding="utf-8") as handle:
            handle.write(text)

    def read_text(self):
        with open(self.data, "r", encoding="utf-8") as handle:
            return handle.read()

    def add(self, name="Widget", price="4.50", quantity="10", file=None):
        argv = ["add", "--name", name, "--price", price, "--quantity", quantity]
        if file is not None:
            return run_tool(["--file", file, *argv])
        return self.run_cli(argv)


class HelpTests(TempFileCase):
    def test_main_help_lists_all_commands(self):
        result = run_tool(["--help"])
        self.assertEqual(result.returncode, 0)
        for command in ["add", "list", "get", "update", "delete", "low-stock", "reorder"]:
            self.assertIn(command, result.stdout)

    def test_main_help_does_not_touch_data_file(self):
        run_tool(["--help"])
        self.assertFalse(self.exists())

    def test_each_command_help_exits_zero(self):
        for command in ["add", "list", "get", "update", "delete", "low-stock", "reorder"]:
            with self.subTest(command=command):
                result = run_tool([command, "--help"])
                self.assertEqual(result.returncode, 0)
                self.assertTrue(result.stdout.strip())

    def test_custom_commands_have_help_pages(self):
        low = run_tool(["low-stock", "--help"])
        self.assertIn("--threshold", low.stdout)
        reorder = run_tool(["reorder", "--help"])
        self.assertIn("--minimum", reorder.stdout)
        self.assertIn("--target", reorder.stdout)


class AddTests(TempFileCase):
    def test_add_creates_file_and_prints_product(self):
        result = self.add(name="  Notebook  ", price="4.5", quantity="10")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        product = parse_json(result.stdout)
        self.assertEqual(product, {"id": 1, "name": "Notebook", "price": "4.50", "quantity": 10})
        self.assertEqual(self.contents(), {"next_id": 2, "products": [product]})

    def test_add_normalizes_price_to_two_decimals(self):
        for raw, stored in [("0", "0.00"), ("4.5", "4.50"), ("4.50", "4.50"), ("12", "12.00")]:
            with self.subTest(raw=raw):
                result = self.add(price=raw)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(parse_json(result.stdout)["price"], stored)

    def test_add_accepts_zero_quantity(self):
        result = self.add(quantity="0")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout)["quantity"], 0)

    def test_add_allows_duplicate_names(self):
        self.add(name="Pen")
        result = self.add(name="Pen")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout)["id"], 2)

    def test_add_ids_increment_and_never_reuse_after_delete(self):
        self.add(name="A")
        self.add(name="B")
        self.run_cli(["delete", "2", "--yes"])
        result = self.add(name="C")
        self.assertEqual(parse_json(result.stdout)["id"], 3)

    def test_add_missing_flag_is_exit_2(self):
        for argv in [
            ["add", "--price", "1.00", "--quantity", "1"],
            ["add", "--name", "X", "--quantity", "1"],
            ["add", "--name", "X", "--price", "1.00"],
        ]:
            with self.subTest(argv=argv):
                result = self.run_cli(argv)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotEqual(result.stderr.strip(), "")

    def test_add_invalid_name_is_exit_2(self):
        for name in ["", "   "]:
            with self.subTest(name=repr(name)):
                result = self.add(name=name)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_add_invalid_price_is_exit_2(self):
        for price in ["-4.50", "$4.50", "4.505", "4.", ".50", "1e2", "4,50", "abc", ""]:
            with self.subTest(price=repr(price)):
                result = self.add(price=price)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_add_invalid_quantity_is_exit_2(self):
        for quantity in ["-1", "1.5", "abc", "", " 3x"]:
            with self.subTest(quantity=repr(quantity)):
                result = self.add(quantity=quantity)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_failed_add_does_not_create_file(self):
        self.add(price="bad")
        self.assertFalse(self.exists())

    def test_failed_add_does_not_consume_id(self):
        self.add(name="A")
        self.add(price="bad")
        result = self.add(name="B")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout)["id"], 2)

    def test_add_missing_parent_directory_fails_without_creating_it(self):
        missing = os.path.join(self.tmp.name, "no_such_dir", "products.json")
        result = self.add(file=missing)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertFalse(os.path.exists(os.path.dirname(missing)))

    def test_add_to_file_in_other_directory(self):
        target = os.path.join(self.tmp.name, "demo.json")
        result = self.add(file=target)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(target))


class ListTests(TempFileCase):
    def test_list_missing_file_prints_empty_array_without_creating_it(self):
        result = self.run_cli(["list"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), [])
        self.assertFalse(self.exists())

    def test_list_sorted_by_id_ascending(self):
        self.add(name="B")
        self.add(name="A")
        result = self.run_cli(["list"])
        names = [product["name"] for product in parse_json(result.stdout)]
        self.assertEqual(names, ["B", "A"])

    def test_list_prints_complete_products(self):
        self.add(name="Pen", price="1.25", quantity="7")
        result = self.run_cli(["list"])
        self.assertEqual(parse_json(result.stdout), [{"id": 1, "name": "Pen", "price": "1.25", "quantity": 7}])


class GetTests(TempFileCase):
    def test_get_existing_product(self):
        self.add(name="Pen", price="1.25", quantity="7")
        result = self.run_cli(["get", "1"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), {"id": 1, "name": "Pen", "price": "1.25", "quantity": 7})

    def test_get_missing_product_is_exit_1(self):
        self.add(name="Pen")
        result = self.run_cli(["get", "9"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("9", result.stderr)

    def test_get_from_missing_file_is_exit_1(self):
        result = self.run_cli(["get", "1"])
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.exists())

    def test_get_invalid_id_is_exit_2(self):
        for product_id in ["0", "-1", "abc", "1.5", ""]:
            with self.subTest(product_id=repr(product_id)):
                result = self.run_cli(["get", product_id])
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")


class UpdateTests(TempFileCase):
    def test_update_single_field(self):
        self.add(name="Pen", price="1.25", quantity="7")
        result = self.run_cli(["update", "1", "--quantity", "99"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), {"id": 1, "name": "Pen", "price": "1.25", "quantity": 99})

    def test_update_all_fields_keeps_id(self):
        self.add(name="Pen", price="1.25", quantity="7")
        result = self.run_cli(["update", "1", "--name", "Pencil", "--price", "2", "--quantity", "0"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), {"id": 1, "name": "Pencil", "price": "2.00", "quantity": 0})

    def test_update_requires_at_least_one_flag(self):
        self.add(name="Pen")
        result = self.run_cli(["update", "1"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_update_invalid_value_leaves_file_unchanged(self):
        self.add(name="Pen", price="1.25", quantity="7")
        before = self.read_text()
        for argv in [["update", "1", "--price", "-2"], ["update", "1", "--quantity", "-3"], ["update", "1", "--name", "  "]]:
            with self.subTest(argv=argv):
                result = self.run_cli(argv)
                self.assertEqual(result.returncode, 2)
        self.assertEqual(self.read_text(), before)

    def test_update_missing_product_is_exit_1(self):
        self.add(name="Pen")
        result = self.run_cli(["update", "5", "--name", "New"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("5", result.stderr)

    def test_update_invalid_id_is_exit_2(self):
        self.add(name="Pen")
        result = self.run_cli(["update", "abc", "--name", "New"])
        self.assertEqual(result.returncode, 2)


class DeleteTests(TempFileCase):
    def test_delete_removes_product_and_prints_deleted_id(self):
        self.add(name="Pen")
        result = self.run_cli(["delete", "1", "--yes"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), {"deleted_id": 1})
        self.assertEqual(self.contents(), {"next_id": 2, "products": []})

    def test_delete_without_yes_is_exit_2(self):
        self.add(name="Pen")
        result = self.run_cli(["delete", "1"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(self.exists())

    def test_delete_missing_product_is_exit_1(self):
        self.add(name="Pen")
        result = self.run_cli(["delete", "7", "--yes"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("7", result.stderr)

    def test_delete_keeps_next_id_unchanged(self):
        self.add(name="A")
        self.add(name="B")
        self.run_cli(["delete", "1", "--yes"])
        self.assertEqual(self.contents()["next_id"], 3)

    def test_delete_invalid_id_is_exit_2(self):
        self.add(name="Pen")
        result = self.run_cli(["delete", "0", "--yes"])
        self.assertEqual(result.returncode, 2)


class LowStockTests(TempFileCase):
    def test_threshold_is_inclusive_and_sorted(self):
        self.add(name="A", quantity="5")
        self.add(name="B", quantity="10")
        self.add(name="C", quantity="4")
        result = self.run_cli(["low-stock", "--threshold", "5"])
        self.assertEqual(result.returncode, 0)
        names = [product["name"] for product in parse_json(result.stdout)]
        self.assertEqual(names, ["A", "C"])

    def test_returns_complete_product_objects(self):
        self.add(name="A", price="2.00", quantity="3")
        result = self.run_cli(["low-stock", "--threshold", "5"])
        self.assertEqual(parse_json(result.stdout), [{"id": 1, "name": "A", "price": "2.00", "quantity": 3}])

    def test_no_matches_prints_empty_array(self):
        self.add(name="A", quantity="50")
        result = self.run_cli(["low-stock", "--threshold", "5"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), [])

    def test_missing_file_prints_empty_array_without_creating_it(self):
        result = self.run_cli(["low-stock", "--threshold", "5"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), [])
        self.assertFalse(self.exists())

    def test_read_only_does_not_modify_existing_file(self):
        self.add(name="A", quantity="3")
        before = self.read_text()
        self.run_cli(["low-stock", "--threshold", "5"])
        self.assertEqual(self.read_text(), before)

    def test_missing_threshold_is_exit_2(self):
        result = self.run_cli(["low-stock"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_invalid_threshold_is_exit_2(self):
        for threshold in ["-1", "1.5", "abc", ""]:
            with self.subTest(threshold=repr(threshold)):
                result = self.run_cli(["low-stock", "--threshold", threshold])
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")


class ReorderTests(TempFileCase):
    def test_plan_matches_and_calculates_quantities(self):
        self.add(name="A", quantity="5")
        self.add(name="B", quantity="10")
        self.add(name="C", quantity="0")
        result = self.run_cli(["reorder", "--minimum", "5", "--target", "20"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            parse_json(result.stdout),
            [
                {"id": 1, "name": "A", "current_quantity": 5, "reorder_quantity": 15},
                {"id": 3, "name": "C", "current_quantity": 0, "reorder_quantity": 20},
            ],
        )

    def test_no_matches_prints_empty_array(self):
        self.add(name="A", quantity="99")
        result = self.run_cli(["reorder", "--minimum", "5", "--target", "20"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), [])

    def test_missing_file_prints_empty_array_without_creating_it(self):
        result = self.run_cli(["reorder", "--minimum", "5", "--target", "20"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(parse_json(result.stdout), [])
        self.assertFalse(self.exists())

    def test_read_only_does_not_modify_existing_file(self):
        self.add(name="A", quantity="3")
        before = self.read_text()
        self.run_cli(["reorder", "--minimum", "5", "--target", "20"])
        self.assertEqual(self.read_text(), before)

    def test_target_not_greater_than_minimum_is_exit_2(self):
        for minimum, target in [("5", "5"), ("5", "4"), ("0", "0")]:
            with self.subTest(minimum=minimum, target=target):
                result = self.run_cli(["reorder", "--minimum", minimum, "--target", target])
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_missing_arguments_is_exit_2(self):
        for argv in [["reorder"], ["reorder", "--minimum", "5"], ["reorder", "--target", "20"]]:
            with self.subTest(argv=argv):
                result = self.run_cli(argv)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_invalid_values_are_exit_2(self):
        for argv in [
            ["reorder", "--minimum", "-1", "--target", "20"],
            ["reorder", "--minimum", "5", "--target", "-2"],
            ["reorder", "--minimum", "x", "--target", "20"],
            ["reorder", "--minimum", "5", "--target", "2.5"],
        ]:
            with self.subTest(argv=argv):
                result = self.run_cli(argv)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")


class FileFlagTests(TempFileCase):
    def test_file_flag_must_precede_command(self):
        result = run_tool(["add", "--file", "x.json", "--name", "A", "--price", "1", "--quantity", "1"])
        self.assertEqual(result.returncode, 2)

    def test_file_flag_before_command_selects_file(self):
        target = os.path.join(self.tmp.name, "other.json")
        result = run_tool(["--file", target, "add", "--name", "A", "--price", "1", "--quantity", "1"])
        self.assertEqual(result.returncode, 0)
        self.assertTrue(os.path.exists(target))
        self.assertFalse(self.exists())

    def test_default_file_is_products_json_in_cwd(self):
        result = run_tool(["add", "--name", "A", "--price", "1", "--quantity", "1"], cwd=self.tmp.name)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.exists())

    def test_relative_path_resolves_from_cwd(self):
        workdir = os.path.join(self.tmp.name, "cwd")
        os.mkdir(workdir)
        result = run_tool(["--file", "sub/data.json", "add", "--name", "A", "--price", "1", "--quantity", "1"], cwd=workdir)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(workdir, "sub")))


class CorruptFileTests(TempFileCase):
    def test_empty_file_is_exit_1_and_left_unchanged(self):
        self.write("")
        for command in [["list"], ["add", "--name", "A", "--price", "1", "--quantity", "1"]]:
            with self.subTest(command=command):
                result = self.run_cli(command)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
        self.assertEqual(self.read_text(), "")

    def test_malformed_json_is_exit_1(self):
        self.write("{not json")
        result = self.run_cli(["list"])
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")

    def test_schema_violations_are_exit_1(self):
        cases = [
            {"next_id": 1},
            {"next_id": 1, "products": [], "extra": True},
            {"next_id": 0, "products": []},
            {"next_id": "1", "products": []},
            {"next_id": 1, "products": {}},
            {"next_id": 1, "products": [{"id": 1, "name": "A", "price": "1.00"}]},
            {"next_id": 1, "products": [{"id": 0, "name": "A", "price": "1.00", "quantity": 1}]},
            {"next_id": 2, "products": [{"id": 1, "name": "A", "price": "1.00", "quantity": 1}, {"id": 1, "name": "B", "price": "1.00", "quantity": 1}]},
            {"next_id": 1, "products": [{"id": 1, "name": "A", "price": "1.00", "quantity": 1}]},
            {"next_id": 2, "products": [{"id": 1, "name": "", "price": "1.00", "quantity": 1}]},
            {"next_id": 2, "products": [{"id": 1, "name": "A", "price": "1", "quantity": 1}]},
            {"next_id": 2, "products": [{"id": 1, "name": "A", "price": 1.0, "quantity": 1}]},
            {"next_id": 2, "products": [{"id": 1, "name": "A", "price": "1.00", "quantity": -1}]},
            {"next_id": 2, "products": [{"id": 1, "name": "A", "price": "1.00", "quantity": True}]},
        ]
        for store in cases:
            with self.subTest(store=store):
                self.write(json.dumps(store))
                result = self.run_cli(["list"])
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")

    def test_corrupt_file_is_not_replaced_by_empty_store(self):
        self.write("{not json")
        self.run_cli(["add", "--name", "A", "--price", "1", "--quantity", "1"])
        self.assertEqual(self.read_text(), "{not json")


class CliSurfaceTests(TempFileCase):
    def test_no_arguments_is_exit_2(self):
        result = run_tool([])
        self.assertEqual(result.returncode, 2)

    def test_unknown_command_is_exit_2(self):
        result = run_tool(["inventory"])
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_flag_is_exit_2(self):
        result = self.run_cli(["list", "--bogus"])
        self.assertEqual(result.returncode, 2)

    def test_unexpected_positional_argument_is_exit_2(self):
        result = self.run_cli(["list", "extra"])
        self.assertEqual(result.returncode, 2)

    def test_errors_have_no_traceback_and_no_stdout_json(self):
        for argv in [["get", "abc"], ["list"], ["--bogus"], ["add", "--name", "A"]]:
            with self.subTest(argv=argv):
                result = self.run_cli(argv)
                self.assertNotIn("Traceback", result.stderr)

    def test_success_prints_only_json_to_stdout(self):
        self.add(name="A", price="1", quantity="1")
        result = self.run_cli(["get", "1"])
        payload = parse_json(result.stdout)
        self.assertEqual(payload["id"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
