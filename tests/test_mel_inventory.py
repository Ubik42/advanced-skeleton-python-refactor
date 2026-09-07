from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adv_migration.mel_inventory import inventory


class InventoryTests(unittest.TestCase):
    def test_handles_comments_strings_and_dependencies(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.mel"
            source.write_text(
                '''global int $shared;
global proc string helper(string $value) {
    string $brace = "}";
    return $value;
}
global proc main() {
    // helper("ignored"); }
    string $value = `helper("ok")`;
    evalDeferred("print \\\"done\\\"");
}
''',
                encoding="utf-8",
            )

            result = inventory(source)

        self.assertEqual([proc.name for proc in result.procedures], ["helper", "main"])
        self.assertEqual(result.procedures[1].calls, ("helper",))
        self.assertEqual(result.procedures[1].dynamic_eval_count, 1)
        self.assertEqual(result.global_variables, ("shared",))


if __name__ == "__main__":
    unittest.main()
