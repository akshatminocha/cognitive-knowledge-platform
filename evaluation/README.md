# Evaluation Suite

This directory contains the custom, lightweight evaluation framework for the Cognitive Knowledge Platform (v2). It is designed to quickly test how well the agent navigates the MCP tools without relying on heavy third-party evaluation suites.

## Evaluation Metrics

When you run the benchmark suite against the `golden_qa.json` dataset, the following 4 core metrics are tracked:

1. **Answer Similarity (Token/Semantic Overlap):** 
   The core metric is `_token_overlap_score(expected, actual)`. It compares the exact text of the Agent's generated answer against the "perfect" expected answer defined in the golden dataset. 

2. **Accuracy (Pass/Fail):** 
   The engine has a configurable `similarity_threshold`. If the similarity score of an answer is above the threshold, the question is marked as `is_correct = True`. Overall Accuracy is calculated as `(Total Correct / Total Questions)`.

3. **Latency (Performance Tracking):** 
   Tracks the exact time (in milliseconds) it takes for the agent to receive the prompt, decide which tools to use, execute the MCP server queries, reflect on the answer, and return the final string.

4. **Categorical Breakdowns:** 
   Because our `golden_qa.json` dataset labels every question with a `category` (e.g., "Multi-Hop Reasoning", "Direct Retrieval") and a `difficulty` (Easy, Medium, Hard), the evaluator automatically aggregates the accuracy and similarity scores across these dimensions. This helps pinpoint exactly where the agent is failing (e.g., if it struggles with multi-hop queries but excels at direct retrieval).

## Running Benchmarks

**Offline mode (validates the pipeline, mocks the LLM):**
```bash
uv run python -m evaluation.run_benchmarks --offline
```

**Full benchmark mode (makes live LLM calls):**
```bash
uv run python -m evaluation.run_benchmarks --model gemini-2.5-flash
```
