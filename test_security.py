import unittest

from security import hash_password, verify_password


class PasswordHashTests(unittest.TestCase):
    def test_hash_verifies_original_password(self):
        stored_hash = hash_password("correct horse battery staple")

        self.assertTrue(verify_password("correct horse battery staple", stored_hash))
        self.assertFalse(verify_password("wrong password", stored_hash))

    def test_hashes_use_independent_salts(self):
        first_hash = hash_password("same password")
        second_hash = hash_password("same password")

        self.assertNotEqual(first_hash, second_hash)
        self.assertTrue(verify_password("same password", first_hash))
        self.assertTrue(verify_password("same password", second_hash))

    def test_malformed_hash_is_rejected(self):
        self.assertFalse(verify_password("password", "not-a-valid-hash"))


if __name__ == "__main__":
    unittest.main()
