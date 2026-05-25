import unittest

from ask_chatbot.pdf_processing import DocumentChunk, chunk_text
from ask_chatbot.prompts import build_prompt
from ask_chatbot.response_cleaning import clean_model_response, clean_partial_model_response
from ask_chatbot.retrieval import representative_chunks, retrieve_relevant_chunks


class ResponseCleaningTests(unittest.TestCase):
    def test_removes_reasoning_tags_and_control_sequences(self):
        raw = "\x1b[32m<think>hidden reasoning</think>\nFinal answer.\x00"
        self.assertEqual(clean_model_response(raw), "Final answer.")

    def test_partial_response_hides_unfinished_think_block(self):
        raw = "Visible\n<think>unfinished hidden text"
        self.assertEqual(clean_partial_model_response(raw), "Visible")


class PdfChunkingTests(unittest.TestCase):
    def test_chunk_text_splits_long_text(self):
        text = " ".join(f"word{i}" for i in range(600))
        chunks = chunk_text(text, max_chars=500, overlap_chars=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 560 for chunk in chunks))


class RetrievalTests(unittest.TestCase):
    def test_retrieval_prefers_matching_chunk(self):
        chunks = [
            DocumentChunk("a.pdf", 1, 1, "This page is about registration deadlines and forms."),
            DocumentChunk("a.pdf", 2, 1, "This page is about campus parking and maps."),
        ]

        results = retrieve_relevant_chunks("registration form deadline", chunks, limit=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.page_number, 1)
        self.assertEqual(results[0].label, "S1")

    def test_representative_chunks_labels_broad_context(self):
        chunks = [DocumentChunk("a.pdf", index + 1, 1, f"Page {index + 1}") for index in range(10)]

        results = representative_chunks(chunks, limit=3)

        self.assertEqual(len(results), 3)
        self.assertEqual([result.label for result in results], ["S1", "S2", "S3"])


class PromptTests(unittest.TestCase):
    def test_prompt_contains_cited_sources_and_injection_warning(self):
        chunk = DocumentChunk("guide.pdf", 7, 1, "Tuition is due before the first week.")
        retrieved = retrieve_relevant_chunks("When is tuition due?", [chunk], limit=1)

        prompt = build_prompt("When is tuition due?", retrieved_chunks=retrieved, has_documents=True)

        self.assertIn("[S1] guide.pdf, page 7", prompt)
        self.assertIn("untrusted reference material", prompt)
        self.assertIn("cite them like [S1]", prompt)


if __name__ == "__main__":
    unittest.main()
