import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import io
import json

# Import the app (we might need to mock LLM before import if it calls it at top level)
# but in our implementation, it's called inside the path operation.
from pdf_parser import app

client = TestClient(app)

class TestPDFParser(unittest.TestCase):

    def test_file_validation_rejects_non_pdf(self):
        """Should reject files that are not application/pdf."""
        response = client.post(
            "/analyze-dpe",
            files={"file": ("test.txt", b"dummy content", "text/plain")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Only PDFs are allowed", response.json()["detail"])

    def test_file_validation_rejects_large_file(self):
        """Should reject files larger than 10MB."""
        large_content = b"0" * (11 * 1024 * 1024)
        response = client.post(
            "/analyze-dpe",
            files={"file": ("large.pdf", large_content, "application/pdf")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("File too large", response.json()["detail"])

    @patch("pdf_parser.extract_text_from_pdf")
    @patch("pdf_parser.analyze_text_with_llm")
    def test_successful_analysis_flow(self, mock_llm, mock_extract):
        """Should return extracted JSON if text and LLM are successful."""
        # 1. Mock text extraction
        mock_extract.return_value = "Numéro DPE: 2134E1234567A\nConsommation: 250 kWh/m2/an"
        
        # 2. Mock LLM response
        mock_llm.return_value = {
            "numero_dpe": "2134E1234567A",
            "etiquette_actuelle": "D",
            "consommation_primaire": 250,
            "surface_habitable": 85.0
        }

        response = client.post(
            "/analyze-dpe",
            files={"file": ("sample.pdf", b"%PDF-1.4...", "application/pdf")}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["data"]["numero_dpe"], "2134E1234567A")
        self.assertEqual(data["data"]["etiquette_actuelle"], "D")
        self.assertIn("raw_text_length", data)

    @patch("pdf_parser.extract_text_from_pdf")
    def test_empty_pdf_error(self, mock_extract):
        """Should return 422 if no text could be extracted."""
        mock_extract.return_value = ""
        
        response = client.post(
            "/analyze-dpe",
            files={"file": ("empty.pdf", b"%PDF-1.4...", "application/pdf")}
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("PDF seems empty", response.json()["detail"])

if __name__ == "__main__":
    unittest.main()
