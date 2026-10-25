import unittest

from pipeline.location import detect_hub, strip_location


class DetectHubTest(unittest.TestCase):
    def test_finds_one_hub(self):
        self.assertEqual(detect_hub("I'm based in Dallas"), "dfw")
        self.assertEqual(detect_hub("run it near Silicon Valley please"), "svalley")
        self.assertEqual(detect_hub("our office is in Salt Lake City"), "slc")

    def test_none_when_absent_or_ambiguous(self):
        self.assertIsNone(detect_hub("fine-tune a 7B model"))
        self.assertIsNone(detect_hub("Dallas or Phoenix"))

    def test_whole_words_only(self):
        self.assertIsNone(detect_hub("a 7B model with iowanian data"))

    def test_strip_location_keeps_the_job(self):
        self.assertEqual(strip_location("I want to fine-tune a model in Dallas"), "I want to fine-tune a model")
        self.assertEqual(strip_location("LoRA fine-tune a 13B model in 3 days, Atlanta"), "LoRA fine-tune a 13B model in 3 days")
        self.assertEqual(strip_location("I'm in Salt Lake City"), "")
        self.assertEqual(strip_location("I'm in Dallas"), "")


if __name__ == "__main__":
    unittest.main()
