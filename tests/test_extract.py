import unittest

from tdoc_converter.extract import extract_statements


def labels(md):
    return [(s.kind, s.id) for s in extract_statements(md)]


class ExtractTest(unittest.TestCase):
    def test_bold_italic_label_with_bullets(self):
        md = ("***Proposal 2-1-1:*** *Support the following:*\n\n* *DPS*\n* *CJT*\n\nBesides, more text.\n\n"
              "* analysis bullet\n")
        (s,) = extract_statements(md)
        self.assertEqual((s.kind, s.id), ("Proposal", "2-1-1"))
        self.assertEqual(s.text, "Support the following:\n- DPS\n- CJT")

    def test_observation_and_plain_label(self):
        md = "Observation 2-6-1: For interleaved mapping,\n  + sub point\n\nNext paragraph.\n"
        (s,) = extract_statements(md)
        self.assertEqual(s.label, "Observation 2-6-1")
        self.assertIn("sub point", s.text)
        self.assertNotIn("Next paragraph", s.text)

    def test_period_separator_and_list_prefix(self):
        md = "***Proposal 1. RAN1 to study X.**\n\n3. Proposal 2: Support Y.\n"
        self.assertEqual(labels(md), [("Proposal", "1"), ("Proposal", "2")])

    def test_label_only_line_takes_following_block(self):
        md = "**Proposal 1**\n\n* Support option 2\n\nFDRA\n\n**Observation 1**\n\nThe drawback is Z.\n"
        got = {s.label: s.text for s in extract_statements(md)}
        self.assertEqual(got["Proposal 1"], "Support option 2")
        self.assertEqual(got["Observation 1"], "The drawback is Z.")

    def test_repeated_label_in_text_is_stripped(self):
        (s,) = extract_statements("***Proposal 2: Proposal 2: Prefer A.***\n")
        self.assertEqual(s.text, "Prefer A.")

    def test_table_rows_and_prose_mentions_are_ignored(self):
        md = ("| **Proposal 4-8-1**   * quoted agreement |\n| --- |\n\n"
              "As in Proposal 1: we agree. The observation: nothing.\n\nProposals are listed below.\n")
        self.assertEqual(labels(md), [])

    def test_conclusion_duplicate_is_merged_keeping_longest(self):
        md = ("## Body\n\nProposal 1: Short.\n\n# Conclusion\n\nProposal 1: Short, with more detail.\n")
        (s,) = extract_statements(md)
        self.assertEqual(s.occurrences, 2)
        self.assertEqual(s.text, "Short, with more detail.")
        self.assertEqual(s.section, "Body")

    def test_image_links_are_not_part_of_statements(self):
        md = "Proposal 1: Support A.\n![fig](images/R1-1/img001.png)\n\n![](images/R1-1/img002.png)\n"
        (s,) = extract_statements(md)
        self.assertEqual(s.text, "Support A.")

    def test_stops_at_heading_and_caption(self):
        md = "Proposal 1: A.\n## Next\nObservation 1: B.\nFigure 3 shows it.\n"
        got = extract_statements(md)
        self.assertEqual([s.text for s in got], ["A.", "B."])


if __name__ == "__main__":
    unittest.main()
