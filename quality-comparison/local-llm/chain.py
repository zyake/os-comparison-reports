import os
from typing import TypedDict, Annotated, List
import operator  # Ensure this is imported for merging concurrent lists
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

# --- Configuration for LM Studio ---
os.environ["OPENAI_API_KEY"] = "lm-studio" 
# Ensure this matches your LM Studio server settings (usually port 1234)
os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1234/v1"

# Initialize the LLM (Local Model)
llm = ChatOpenAI(
    model="qwen3.6-35b-a3b", # Or your specific local model name
    temperature=0.7,         # Higher temp can sometimes help with creative/longer outputs
    max_tokens=15000          # Increased limit to allow for longer responses
)

# --- State Definition ---
class AgentState(TypedDict):
    research_topics: List[str] 
    research_results: dict     
    # FIX 2: Use Annotated with operator.add to merge lists from concurrent nodes
    reviews: Annotated[List[str], operator.add] 
    final_output: str          

# --- Node 1: Researcher Agent (Enhanced for Length) ---
def researcher_node(state: AgentState):
    print("--- RESEARCHING (DEEP DIVE) ---")
    topics = state["research_topics"]
    results = {}

    for topic in topics:
        response = llm.invoke(f"""
        Act as a Senior Technical Researcher. Provide an EXHAUSTIVE and DETAILED analysis of the {topic} Operating System 
        specifically for Local LLM Deployment. Do not summarize; provide full technical depth.

        Your report must include:
        1. OS Architecture & Kernel Tuning: Specific kernel parameters (sysctl) to optimize for AI workloads.
        2. Hardware Interaction: How the OS handles VRAM/RAM allocation, PCIe lane management, and NVMe caching.
        3. Software Ecosystem: Detailed compatibility with Docker, Python virtual environments, CUDA/ROCm drivers, and specific library versions (e.g., PyTorch 2.1+).
        4. Performance Benchmarks: Theoretical and real-world inference speeds (tokens/sec) for various quantization levels (Q4, Q5, Q8).
        5. Known Issues: List specific bugs or incompatibilities with local AI tools (Ollama, vLLM, llama.cpp).

        Return the result in JSON format: {{"topic": "{topic}", "summary": "...", "pros": [...], "cons": [...]}}
        """)
        results[topic] = response.content
    return {"research_results": results}

# --- Node 2: Reviewer Agents (Enhanced for Length) ---
def security_reviewer(state: AgentState):
    print("--- SECURITY REVIEWER (DEEP DIVE) ---")
    feedback = []
    for topic, content in state["research_results"].items():
        response = llm.invoke(f"""
        Act as a Lead Cybersecurity Expert. Conduct a DEEP-DIVE security audit of the following research on {topic}.
        Do not just list risks; explain the mechanics of how they could be exploited in a local LLM context.

        Analyze:
        1. Attack Vectors: API exposure risks, model poisoning via untrusted GGUF files, and prompt injection.
        2. Network Security: Firewall configurations required to expose the local server safely (or keep it air-gapped).
        3. Data Privacy: How the OS handles memory swapping and whether sensitive model weights are written to disk unencrypted.
        4. Mitigation Strategies: Provide specific, copy-pasteable configuration commands to harden the {topic} OS.

        Research Content: {content}
        """)
        feedback.append(f"Security Review for {topic}: {response.content}")
    return {"reviews": feedback}

def performance_reviewer(state: AgentState):
    print("--- PERFORMANCE REVIEWER (DEEP DIVE) ---")
    feedback = []
    for topic, content in state["research_results"].items():
        # FIX 3: Changed 'lll' to 'llm' (typo fix)
        response = llm.invoke(f"""
        Act as a Hardware Performance Engineer. Provide a GRANULAR performance analysis of {topic} for Local LLMs.
        Focus on optimization techniques and hardware utilization.

        Analyze:
        1. Inference Speed: Detailed breakdown of tokens per second (TPS) for different batch sizes and context lengths.
        2. Quantization Impact: How Q4_K_M vs FP16 affects memory bandwidth and latency on {topic}.
        3. Memory Management: How the OS handles large context windows (e.g., 32k+ tokens) without swapping to disk.
        4. Optimization Techniques: Specific compiler flags (e.g., -march=native) or library settings to maximize speed.

        Research Content: {content}
        """)
        feedback.append(f"Performance Review for {topic}: {response.content}")
    return {"reviews": feedback}

# --- Node 3: Aggregator Agent (Enhanced for Length) ---
def aggregator_node(state: AgentState):
    print("--- AGGREGATING RESULTS (COMPREHENSIVE GUIDE) ---")
    research_str = str(state["research_results"])
    review_str = str(state["reviews"])

    response = llm.invoke(f"""
    You are a Principal Technical Lead. Your task is to synthesize the Research Data and Security/Performance Reviews 
    into a MASSIVE, COMPREHENSIVE, and DETAILED "Ultimate Guide to Local LLM Deployment".

    DO NOT SUMMARIZE BRIEFLY. The goal is to create a reference document that an expert would use.

    Structure the guide as follows:
    1. Executive Summary (High-level comparison).
    2. Detailed OS Breakdown: For Windows, macOS, and Linux, include the full technical details from the research phase (kernel tweaks, driver versions).
    3. Security Hardening: Include the specific mitigation commands and risk analysis from the security review.
    4. Performance Optimization: Include the specific benchmarking data and optimization flags from the performance review.
    5. Final Recommendation: A nuanced conclusion on which OS is best for specific hardware setups (e.g., "If you have 64GB RAM and an RTX 4090, use Linux with these specific settings...").

    Ensure the output is long, detailed, and technically rigorous.
    
    1. Research Data: {research_str}
    2. Security Reviews: {review_str}
    """)
    return {"final_output": response.content}

# --- Graph Construction ---
workflow = StateGraph(AgentState)

# 1. Add Nodes
workflow.add_node("researcher", researcher_node)
workflow.add_node("security_reviewer", security_reviewer)
workflow.add_node("performance_reviewer", performance_reviewer)
workflow.add_node("aggregator", aggregator_node)

# 2. Define Edges (The Flow)
workflow.set_entry_point("researcher")

# Researcher -> Reviewers (Concurrent)
workflow.add_edge("researcher", "security_reviewer")
workflow.add_edge("researcher", "performance_reviewer")

# Reviewers -> Aggregator (Wait for all to finish)
workflow.add_edge("security_reviewer", "aggregator")
workflow.add_edge("performance_reviewer", "aggregator")

# Aggregator -> End
workflow.add_edge("aggregator", END)

# Compile the graph
app = workflow.compile()

# --- Execution ---
if __name__ == "__main__":
    initial_state = {
        "research_topics": ["Windows", "macOS", "Linux"],
        "research_results": {},
        "reviews": [], 
        "final_output": ""
    }

# Run the graph
    final_state = app.invoke(initial_state)
    print("\n" + "="*50)
    print("FINAL OUTPUT:")
    print("="*50)
    # Save to file if it's very long, or just print
    print(final_state["final_output"])

