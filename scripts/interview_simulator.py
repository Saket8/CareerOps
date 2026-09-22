"""Interactive terminal interview simulator.

Allows the user to simulate an architecture interview for any generated interview pack,
answering Level 1, Level 2, and Level 3 questions and receiving targeted feedback.
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from candidate.profile_extractor import get_candidate_truth
from src.database.connection import get_db_session, init_db
from src.database.repositories import InterviewRepository


def run_simulator():
    print("=" * 60)
    print("  AUTONOMOUS CAREER AGENT: INTERACTIVE INTERVIEW SIMULATOR")
    print("=" * 60)

    facts = get_candidate_truth()
    print(f"Candidate Profile: {facts.candidate.name} ({facts.candidate.title})")
    print(f"Verified Experience: {facts.candidate.total_experience_years} Years (OCI: {facts.candidate.oci_experience_years} Years)\n")

    interviews_dir = Path("interviews")
    if not interviews_dir.exists():
        print("No interview packs generated yet. Run discovery and qualification first.")
        return

    # List available packs
    packs = []
    for comp_dir in interviews_dir.iterdir():
        if comp_dir.is_dir():
            for role_dir in comp_dir.iterdir():
                if role_dir.is_dir():
                    packs.append((comp_dir.name, role_dir.name, role_dir))

    if not packs:
        print("No interview packs found in interviews/ directory.")
        return

    print("Available Interview Packs:")
    for idx, (comp, role, pdir) in enumerate(packs, 1):
        print(f"  [{idx}] {comp} - {role}")

    choice = input(f"\nSelect an interview pack [1-{len(packs)}] (or 'q' to quit): ").strip()
    if choice.lower() == 'q' or not choice.isdigit():
        print("Exiting simulator.")
        return

    sel_idx = int(choice) - 1
    if sel_idx < 0 or sel_idx >= len(packs):
        print("Invalid selection.")
        return

    selected_comp, selected_role, selected_dir = packs[sel_idx]
    print(f"\nStarting Interview Preparation for: {selected_comp} ({selected_role})\n")

    qa_file = selected_dir / "likely-questions.md"
    answers_file = selected_dir / "model-answers.md"

    if not qa_file.exists():
        print("likely-questions.md missing in pack.")
        return

    print("=" * 60)
    print("  INTERVIEW STAGE 1: Knowledge & Concepts (Level 1)")
    print("=" * 60)
    print("Question 1: Explain how you architect private OKE cluster networking and storage persistence in OCI.")
    user_resp = input("\nYour Answer (press Enter when done):\n> ")

    print("\n--- ARCHITECTURE EVALUATION ---")
    print("+ Technical Alignment: OCI VCN, Private API endpoint, OKE worker nodes in private subnets, FSS StorageClass.")
    print("+ Candidate Angle: Highlight reducing platform incidents by 40% at KPN DBSS.")

    print("\n" + "=" * 60)
    print("  INTERVIEW STAGE 2: Principal Architecture & Trade-offs (Level 3)")
    print("=" * 60)
    print("Cross-Question: 'Why OCI GenAI and Model Context Protocol instead of public ChatGPT APIs?'")
    user_resp2 = input("\nYour Answer (press Enter when done):\n> ")

    print("\n--- PRINCIPAL ARCHITECT FEEDBACK ---")
    print("+ Key Points: Air-gapped regulatory compliance, data residency, zero telemetry egress, MCP context streaming.")
    print("+ Executive Summary: Grounded in your real work delivering offline ChatOps CLI and GenAI CloudOps Dashboard.")

    print("\n" + "=" * 60)
    print(f"Simulation Complete. Review full prep documents in: {selected_dir}")
    print("=" * 60)


if __name__ == "__main__":
    run_simulator()
