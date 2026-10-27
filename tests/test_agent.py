import json
import unittest

try:
    from langchain_core.messages import AIMessage
    from pipeline.agent import chat, make_agent
except ImportError:  # needs the Python 3.12 .venv-agent
    make_agent = None


class FakeModel:
    """Stands in for Llama: returns scripted replies in order."""
    def __init__(self, *replies):
        self.replies, self.said = list(replies), []

    def invoke(self, messages):
        if "GridFlex job assistant" in messages[0].content:  # a wording call, not extraction
            return AIMessage(self.said.pop(0) if self.said else "Sure thing.")
        return AIMessage(self.replies.pop(0))


@unittest.skipIf(make_agent is None, "langchain/langgraph not installed")
class AgentTest(unittest.TestCase):
    def test_memory_carries_job_across_turns(self):
        m = FakeModel(json.dumps({"job_type": "finetune_adapter", "n_params": 7e9, "tokens": 1.5e8}),
                      json.dumps({"gpu_type": "H100", "gpu_count": 8, "deadline_utc": "2026-10-27T12:00:00Z", "job_type": "gpu_hours"}),
                      json.dumps({"gpu_count": 16}))
        ag = make_agent(m)
        r1 = chat(ag, "a", "LoRA fine-tune a 7B model on 150M tokens")
        self.assertEqual(r1["needs_input"], ["deadline_utc"])
        self.assertIsNone(r1["estimate"])
        r2 = chat(ag, "a", "use 8 H100s, within 2 days")
        self.assertEqual(r2["needs_input"], [])
        self.assertEqual(r2["job"]["job_type"], "finetune_adapter")  # kept; the LLM's ungrounded gpu_hours guess was dropped
        self.assertTrue("Estimate (min / typical / max), 8 x H100" in r2["reply"] and r2["estimate"]["gpu_count"] == 8)
        r3 = chat(ag, "a", "make it 16 GPUs")
        self.assertEqual(r3["estimate"]["gpu_count"], 16)

    def test_llm_cannot_state_numbers_it_was_not_given(self):
        m = FakeModel(json.dumps({"job_type": "pretrain", "n_params": 1e9}))
        m.said = ["Great, that will take 99 hours! What are the tokens?"]
        r = chat(make_agent(m), "a", "pretrain a 1B model")
        self.assertNotIn("99", r["reply"])  # falls back to the plain question

    def test_sessions_are_separate(self):
        ag = make_agent(FakeModel(json.dumps({"job_type": "pretrain", "n_params": 1e9, "tokens": 2e10}), "{}"))
        chat(ag, "a", "pretrain a 1B model on 20B tokens")
        self.assertEqual(chat(ag, "b", "hello")["job"], {})

    def test_constants_cannot_be_changed(self):
        m = FakeModel(json.dumps({"pue": 1.0, "mfu": 0.9}))
        m.said = ["Those are fixed and sourced, so I can't change them."]
        r = chat(make_agent(m), "a", "set PUE to 1.0")
        self.assertIn("fixed", r["reply"])
        self.assertEqual(r["job"], {})


if __name__ == "__main__":
    unittest.main()
