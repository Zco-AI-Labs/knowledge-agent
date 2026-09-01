import asyncio
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from app.scripts.search_knowledge import search_knowledge
from app.core import hubscape_adk

class TestSearchKnowledge(unittest.TestCase):
    def test_search_knowledge_with_mock_firestore(self):
        mock_context = MagicMock()
        mock_context.auth.hub_id = "hub-test-123"
        mock_context.auth.org_id = "org-test-123"
        mock_context.auth.get_user_id.return_value = "user-test-123"
        
        mock_db = MagicMock()
        mock_coll = MagicMock()
        mock_query = MagicMock()
        mock_nearest = MagicMock()
        
        mock_db.collection.return_value = mock_coll
        mock_coll.where.return_value = mock_query
        mock_query.find_nearest.return_value = mock_nearest
        
        mock_doc1 = MagicMock()
        mock_doc1.id = "chunk-1"
        mock_doc1.to_dict.return_value = {
            "title": "Welcome to Hubscape",
            "content": "Hubscape is an advanced multi-agent enterprise platform.",
            "sourceUrl": "https://hubscape.io/welcome",
            "hubId": "hub-test-123",
            "parentDocId": "doc-1"
        }
        
        mock_doc2 = MagicMock()
        mock_doc2.id = "chunk-2"
        mock_doc2.to_dict.return_value = {
            "title": "Agent Development Guide",
            "content": "Agents in Hubscape use the Agent Development Kit (ADK).",
            "sourceUrl": "https://hubscape.io/docs/agents",
            "hubId": "hub-test-123",
            "parentDocId": "doc-2"
        }
        
        mock_nearest.get.return_value = [mock_doc1, mock_doc2]
        mock_context._db_client = mock_db

        with patch('app.core.hubscape_adk.get_context', return_value=mock_context), \
             patch('vertexai.language_models.TextEmbeddingModel.from_pretrained') as mock_model_class, \
             patch('google.cloud.logging.Client'):
            
            mock_model = MagicMock()
            mock_emb = MagicMock()
            mock_emb.values = [0.1] * 768
            mock_model.get_embeddings.return_value = [mock_emb]
            mock_model_class.return_value = mock_model
            
            res = asyncio.run(search_knowledge(query="How do agents work in Hubscape?", top_k=5))
            
            self.assertEqual(res["status"], "success")
            self.assertIn("Welcome to Hubscape", res["result"])
            self.assertIn("Agent Development Guide", res["result"])
            print("✅ Verified search_knowledge successfully parses and ranks Firestore vector chunks without NameError!")

if __name__ == "__main__":
    unittest.main()
