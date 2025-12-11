import os
import re
import json
from datetime import datetime
import mysql.connector
from zhipuai import ZhipuAI

# -------------------------
# database
# -------------------------
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "123456",
    "database": "agent_room",
    "auth_plugin": "mysql_native_password"
}

# -------------------------
# -------------------------
API_KEY = os.getenv("ZHIPUAI_API_KEY", "Your api key")
client = ZhipuAI(api_key=API_KEY)

# -------------------------
def save_log(story_id, request_msg, response_msg, log_type):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            INSERT INTO story_logs (story_id, request_message, response_message, timestamp, type)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (story_id, request_msg, response_msg, timestamp, log_type))
        conn.commit()
    except Exception as e:
        print(f"[DB ERROR] write log error: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

# -------------------------
def extract_write_identifiers(plan_dict, story_dict):
    plan_sections = list(plan_dict.keys())
    story_sections = list(story_dict.keys())
    identifiers = "a Creative Writing Task"
    if plan_sections:
        identifiers += f", the {', '.join(plan_sections)}"
    if story_sections:
        identifiers += f", and the Previous Sections ({', '.join(story_sections)})"
    return identifiers

# -------------------------
def call_agent_for_write(client, prompt, context_text, story_id, log_type="write"):
    request_text = f"{prompt}\n{context_text}"
    messages = [
        {"role": "system", "content": "You are a creative writing assistant following the given prompt strictly."},
        {"role": "user", "content": request_text}
    ]


    print("\n--- Sending to LLM (WRITE stage) ---")
    print("REQUEST:\n", request_text)

    try:
        response = client.chat.completions.create(
            model="glm-4-air",
            messages=messages,
        )
        output = response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] LLM call error: {e}")
        output = f"[ERROR] LLM call error: {e}"

    print("\nRESPONSE:\n", output)
    print("--- End LLM response ---\n")

    try:
        save_log(story_id, request_text, output, log_type)
    except Exception as e:
        print(f"[WARN] log error: {e}")

    return output


# -------------------------
def generate_write_only(story_id, plan_dict, creative_writing_task):
    story_dict = {}
    sections = ["Exposition", "Rising Action", "Climax", "Falling Action", "Resolution"]
    dimensions = ["Story Structure", "Originality", "Depth", "Style", "Task Alignment"]
    max_iterations = 1  # per section

    for i, section in enumerate(sections):
        # Prior sections summary (if any)
        prior_summary = ""
        if i > 0:
            prior_summary_prompt = (
                "Beam Focusing: summarize the previous story sections concisely, focusing on plot progression, character arcs, and key details "
                "while preserving the original task's requirements. Retain sufficient details for expansive story generation. Output a compact beam-focused summary."
            )
            prior_context = f"Original Task: {creative_writing_task}\n\nPrevious Sections: {json.dumps({s: story_dict[s] for s in sections[:i]}, ensure_ascii=False)}"
            prior_summary = call_agent_for_write(client, prior_summary_prompt, prior_context, story_id, log_type=f"prism_beam_focusing_prior_{section}")

        # Writer Phase: Generate initial draft
        writer_prompt = (
            f"Given <identifiers found in the scratchpad> (Creative Writing Task, Central Conflict, Character Descriptions, Setting, Key Plot Points, and Previous Sections), continue the story by writing the {section} part. Generate detailed, expansive content. "
            "Begin your portion of the story in a way that naturally flows from the previous ending. Match the writing style, vocabulary, and overall mood of the existing text. Do not re-explain details or events that have already been described. "
            "Focus only on the {section} part of the story. Do not write about the following parts of the story. Do not end the story (unless Resolution). Ensure fidelity to the original task."
        ).replace("<identifiers found in the scratchpad>", extract_write_identifiers(plan_dict, story_dict))
        writer_context = f"Original Task: {creative_writing_task}\n\nPlan: {json.dumps(plan_dict, ensure_ascii=False)}\n\nPrevious Sections Summary: {prior_summary}"
        section_output = call_agent_for_write(client, writer_prompt, writer_context, story_id, log_type=f"prism_weave_{section}")
        story_dict[section] = section_output

        need_refine = False  # Flag for refinement

        # Section Beam Focusing Phase (temporary)
        section_summary_prompt = (
            "Beam Focusing: summarize the current story so far (including the new section) concisely, focusing on plot progression, character arcs, and key details "
            "while preserving the original task's requirements. Retain sufficient details for expansive refinement. Output a compact beam-focused summary."
        )
        section_summary_context = f"Original Task: {creative_writing_task}\n\nPlan: {json.dumps(plan_dict, ensure_ascii=False)}\n\nCurrent Story Sections: {json.dumps(story_dict, ensure_ascii=False)}"
        section_summary = call_agent_for_write(client, section_summary_prompt, section_summary_context, story_id, log_type=f"prism_beam_focusing_section_{section}")

        # Spectrum Conference Phase (temporary, single-round dialogue)
        debate_prompt = (
            "Initiate a Spectrum Conference: given the beam-focused summary of the section, run a single-round multi-agent collaborative discussion. Assign roles adaptively: Coherence Coordinator (structure), Innovator (originality), Expander (depth), Stylist (style). "
            "Agents should exchange ideas synergistically: debate improvements, reflect briefly on others' ideas, and build toward unified suggestions. Produce a transcript (more than 10 exchanges) and conclude with consolidated, actionable suggestions aligned with the original task."
        )
        debate_context = f"Original Task: {creative_writing_task}\n\nBeam Focused Summary: {section_summary}"
        debate_output = call_agent_for_write(client, debate_prompt, debate_context, story_id, log_type=f"prism_spectrum_conference_{section}")

        # Spectral Analysis Phase (temporary, parallel)
        critiques = ""
        grade_counts = {"A": 0, "B": 0, "C": 0}
        for dim in dimensions:
            critique_prompt = (
                f"Perform Spectral Analysis for one spectrum band: {dim}. "
                f"For {dim} Analyst: Assess {'coherence, consistency, and progression' if dim=='Story Structure' else 'innovation, avoidance of clichés, and novel elements' if dim=='Originality' else 'character/setting richness and believability' if dim=='Depth' else 'variety, devices, and expressiveness' if dim=='Style' else 'adherence to original task (e.g., key elements, perspective, implications)'} (grade A/B/C, with evidence). "
                "Start with Grade: X\nThen bullet points with suggestions. Ensure suggestions align with the original task."
            )
            critique_context = f"Original Task: {creative_writing_task}\n\nBeam Focused Summary: {section_summary}\n\nSpectrum Conference Transcript: {debate_output}"
            critique_output = call_agent_for_write(client, critique_prompt, critique_context, story_id, log_type=f"prism_spectral_analysis_{section}_{dim}")
            critiques += f"\n{dim} Spectral Analysis:\n{critique_output}"
            # Extract grade
            grade_match = re.search(r'Grade: (A|B|C)', critique_output, re.IGNORECASE)
            if grade_match:
                grade = grade_match.group(1).upper()
                grade_counts[grade] += 1

        # Focal Decision Phase (temporary)
        decision_prompt = (
            "Conduct a Focal Decision: given the spectral analyses (temporary), determine revisions for the section. Calculate majority grade (A/B/C by count). Output category: 'Severe (majority C)' / 'Major (majority B)' / 'Minor (majority A with B)' / 'No Issue (all A)', with reasons and confidence (High/Medium/Low). If <B, suggest targeted fixes."
        )
        decision_context = f"Spectral Analyses: {critiques}"
        decision_output = call_agent_for_write(client, decision_prompt, decision_context, story_id, log_type=f"prism_focal_decision_{section}")

        # Parse decision category
        category_match = re.search(r'category: \'(Severe|Major|Minor|No Issue)\'', decision_output, re.IGNORECASE)
        if category_match:
            category = category_match.group(1).upper()
            if category in ['SEVERE', 'MAJOR']:
                need_refine = True
                # Extract suggestions for refine
                suggestions = re.search(r'suggest targeted fixes:\s*(.*)', decision_output, re.DOTALL | re.IGNORECASE)
                refine_suggestions = suggestions.group(1).strip() if suggestions else ""
            else:
                need_refine = False
        else:
            need_refine = True  # Default to refine if parse fails
            refine_suggestions = ""

        # Beam Reforging Phase (if needed, overwrite story_dict)
        if need_refine:
            refine_prompt = (
                f"Perform Beam Reforging: given the beam-focused summary, spectral analyses, and focal decision suggestions (temporary), refine the {section}. Inject creative elements if Originality grade <B. Generate detailed, expansive refinements. "
                f"Output: {section}: <refined text> Ensure refinements match original task's style and requirements."
            )
            refine_context = f"Original Task: {creative_writing_task}\n\nBeam Focused Summary: {section_summary}\n\nDecision Suggestions: {refine_suggestions}\n\nSpectral Analyses: {critiques}"
            refine_output = call_agent_for_write(client, refine_prompt, refine_context, story_id, log_type=f"prism_beam_reforging_{section}")

            # Extract refined section (more flexible regex)
            refined_match = re.search(re.escape(section) + r'\s*:\s*(.*)', refine_output, re.DOTALL | re.IGNORECASE)
            if refined_match:
                refined_section = refined_match.group(1).strip()
                story_dict[section] = refined_section
            else:
                print(f"[WARN] Refined {section} failed to parse. Retrying with format fix.")
                # Retry with format fix
                retry_refine_prompt = refine_prompt + " Strictly follow the output format with exact key."
                retry_refine_output = call_agent_for_write(client, retry_refine_prompt, refine_context, story_id, log_type=f"prism_beam_reforging_retry_{section}")
                retry_match = re.search(re.escape(section) + r'\s*:\s*(.*)', retry_refine_output, re.DOTALL | re.IGNORECASE)
                if retry_match:
                    story_dict[section] = retry_match.group(1).strip()
                else:
                    print(f"[WARN] Retry failed for {section}. Keeping current.")

    # Final Supervisor Synthesis (Beam Focusing for full and synthesis)
    full_summary_prompt = (
        "Beam Focusing: summarize all refined sections concisely, focusing on overall plot, character arcs, and key details "
        "while preserving the original task's requirements. Retain sufficient details for expansive story generation. Output a compact beam-focused summary."
    )
    full_summary_context = f"Original Task: {creative_writing_task}\n\nRefined Sections: {json.dumps(story_dict, ensure_ascii=False)}"
    full_summary = call_agent_for_write(client, full_summary_prompt, full_summary_context, story_id, log_type="prism_full_summary")

    synthesis_prompt = (
        "Given all refined sections from story dict, synthesize the full story. Ensure overall coherence, resolve any inconsistencies, and optimize for all dimensions. Generate a complete, expansive narrative. "
        "Output the complete narrative, strictly following the original task (e.g., perspective, ignoring word limits for fuller content)."
    )
    synthesis_context = f"Original Task: {creative_writing_task}\n\nFull Sections Summary: {full_summary}\n\nRefined Sections: {json.dumps(story_dict, ensure_ascii=False)}"
    synthesis_output = call_agent_for_write(client, synthesis_prompt, synthesis_context, story_id, log_type="prism_write_synthesis")
    story_dict["Full Story"] = synthesis_output

    return story_dict

# -------------------------
def extract_full_story_from_story_dict(story_dict):
    if "Full Story" in story_dict:
        return story_dict["Full Story"].strip()

    sections = ["Exposition", "Rising Action", "Climax", "Falling Action", "Resolution"]
    full = [story_dict.get(sec, "").strip() for sec in sections if sec in story_dict]
    if full:
        return "\n\n".join(full)

    return ""

# -------------------------
def main(example_id=None, story_id=None, plan_path=None, plan_file=None, output_dir=None, output_txt=None, output_json=None):
    sid = example_id or story_id or "example_unknown"

    plan_path = plan_path or plan_file

    if output_txt is None:
        if output_dir:
            output_txt = os.path.join(output_dir, "story_text.txt")
        else:
            output_txt = os.path.join(os.getcwd(), "story_text.txt")
    if output_json is None:
        if output_dir:
            output_json = os.path.join(output_dir, "story_write.json")
        else:
            output_json = os.path.join(os.getcwd(), "story_write.json")

    plan_dict = None
    creative_writing_task = ""
    if plan_path and os.path.exists(plan_path):
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "plan" in data:
                plan_dict = data["plan"]
            if "task" in data:
                creative_writing_task = data["task"]

            elif isinstance(data, dict) and "scratchpad" in data:
                # Parse old scratchpad to dict
                scratchpad = data["scratchpad"]
                plan_dict = {}
                for key in ["Central Conflict", "Character Descriptions", "Setting", "Key Plot Points"]:
                    match = re.search(r'\[' + re.escape(key) + r'\]\s*(.*?)(?=\[|\Z)', scratchpad, re.DOTALL)
                    if match:
                        plan_dict[key] = match.group(1).strip()
                if "task" in data:
                    creative_writing_task = data["task"]
                else:
                    task_match = re.search(r'\[Creative Writing Task\]\s*(.*?)(?=\[|\Z)', scratchpad, re.DOTALL)
                    if task_match:
                        creative_writing_task = task_match.group(1).strip()
        except Exception as e:
            print(f"[WARN] read plan_path failed ({plan_path}): {e}")
            plan_dict = None

    if not plan_dict:

        print("[WARN] no valid plan dict，generate_write_only")
        plan_dict = {}
        creative_writing_task = ""

    story_dict = generate_write_only(sid, plan_dict, creative_writing_task)

    full_story = extract_full_story_from_story_dict(story_dict)

    result = {
        "example_id": sid,
        "full_story": full_story,
        "story_dict": story_dict,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(output_json), exist_ok=True)
    except Exception:
        pass

    try:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[INFO] Write JSON written to {output_json}")
    except Exception as e:
        print(f"[WARN] write error {output_json}: {e}")

    try:
        with open(output_txt, "w", encoding="utf-8") as f:
            f.write(full_story)
        print(f"[INFO] Story text written to {output_txt}")
    except Exception as e:
        print(f"[WARN] write error {output_txt}: {e}")

    return result

# -------------------------
if __name__ == "__main__":
    sid = os.environ.get("STORY_ID", os.environ.get("example_id", "example_unknown"))
    planp = os.environ.get("PLAN_PATH", os.environ.get("plan_path", os.environ.get("PLAN", None)))
    outdir = os.environ.get("OUTPUT_DIR", os.environ.get("OUTPUT", None))

    out_txt = None
    out_json = None
    if outdir:
        try:
            os.makedirs(outdir, exist_ok=True)
            out_txt = os.path.join(outdir, "story_text.txt")
            out_json = os.path.join(outdir, "story_write.json")
        except Exception:
            out_txt = None
            out_json = None

    main(example_id=sid, plan_path=planp, output_dir=outdir, output_txt=out_txt, output_json=out_json)