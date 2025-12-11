import os
import re
from datetime import datetime
import mysql.connector
from zhipuai import ZhipuAI
import json

# -------------------------
# Database connection config (same as original)
# -------------------------
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "123456",
    "database": "agent_room",
    "auth_plugin": "mysql_native_password"
}

# -------------------------
# ZhipuAI client config
# -------------------------
API_KEY = os.getenv("ZHIPUAI_API_KEY", "Your api key")
client = ZhipuAI(api_key=API_KEY)

# -------------------------
# Helper: save logs to database
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
        print(f"[DB ERROR] failed to write log: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

# -------------------------
# Plan internal utilities
# -------------------------
def extract_plan_identifiers(plan_dict):
    sections = list(plan_dict.keys())
    if sections:
        return ", ".join(
            ["a Creative Writing Task" if s == "Creative Writing Task" else f"the {s}" for s in sections]
        )
    return "a Creative Writing Task"

def call_agent_for_plan(client, prompt, context_text, story_id, log_type="plans"):
    request_text = f"{prompt}\n{context_text}"
    messages = [
        {"role": "system", "content": "You are a creative writing assistant following the given prompt strictly."},
        {"role": "user", "content": request_text}
    ]
    try:
        response = client.chat.completions.create(
            model="glm-4-air",
            messages=messages,
        )
        output = response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        output = f"[ERROR] LLM call failed: {e}"

    print(f"\n=== {log_type.upper()} STAGE OUTPUT (story_id={story_id}) ===")
    print("REQUEST:\n", request_text)
    print("RESPONSE:\n", output)

    try:
        save_log(story_id, request_text, output, log_type)
    except Exception as e:
        print(f"[WARN] failed to save log: {e}")

    return output

# -------------------------
# Main logic: generate plan and return plan_dict (dict)
# NOTE: logic unchanged; only terms/prompts/log tags updated to Prism terminology:
# Beam Focusing, Spectrum Conference, Spectral Analysis, Focal Decision, Beam Reforging
# -------------------------
def generate_plan_only(story_id, creative_writing_task):
    plan_dict = {}

    # Draft: Initial Central Conflict
    conflict_prompt = (
        "Given <identifiers found in the plan>, describe the central conflict in detail (more than 5 sentences). "
        "The description should answer the following questions: "
        "⋆ What’s the protagonist’s main goal in this story? "
        "⋆ Why do they want it? "
        "⋆ What’s stopping them from achieving it?"
    ).replace("<identifiers found in the plan>", extract_plan_identifiers(plan_dict))
    conflict_context = f"Original Task: {creative_writing_task}"
    conflict_output = call_agent_for_plan(client, conflict_prompt, conflict_context, story_id, log_type="prism_devise_conflict")
    plan_dict["Central Conflict"] = conflict_output

    # Draft: Initial Character Descriptions (subscribe to Conflict)
    character_prompt = (
        "Given <identifiers found in the plan>, describe the characters in detailed bullet points (more than 5 sentences for each character). "
        "The description should answer the following questions: "
        "⋆ What do the characters sound like? Are they talkative or quiet? What kind of slang do they use? What is their sense of humor like? "
        "⋆ What do they look like? Do they have any defining gestures? What’s the first thing people notice about them? "
        "⋆ What are their motivations and internal characteristics? What are their flaws? What are their values? What are they afraid of? "
        "How will they change and grow over the course of this story?"
    ).replace("<identifiers found in the plan>", extract_plan_identifiers(plan_dict))
    character_context = f"Original Task: {creative_writing_task}\n\nPlan so far: {json.dumps(plan_dict, ensure_ascii=False)}"
    character_output = call_agent_for_plan(client, character_prompt, character_context, story_id, log_type="prism_devise_character")
    plan_dict["Character Descriptions"] = character_output

    # Draft: Initial Setting (subscribe to upstream)
    setting_prompt = (
        "Given <identifiers found in the plan>, describe the setting in detail (more than 5 sentences). "
        "The description should answer the following questions: "
        "⋆ Where does the story take place? Is it set in a fictional world, or is it simply set in someone’s backyard? "
        "⋆ When does the story take place? What decade is it set in? How much time elapses over the course of the story?"
    ).replace("<identifiers found in the plan>", extract_plan_identifiers(plan_dict))
    setting_context = f"Original Task: {creative_writing_task}\n\nPlan so far: {json.dumps(plan_dict, ensure_ascii=False)}"
    setting_output = call_agent_for_plan(client, setting_prompt, setting_context, story_id, log_type="prism_devise_setting")
    plan_dict["Setting"] = setting_output

    # Draft: Initial Key Plot Points (subscribe to all upstream)
    plot_prompt = (
        "Given <identifiers found in the plan>, describe the key plot points in detailed bullet points."
    ).replace("<identifiers found in the plan>", extract_plan_identifiers(plan_dict))
    plot_context = f"Original Task: {creative_writing_task}\n\nPlan so far: {json.dumps(plan_dict, ensure_ascii=False)}"
    plot_output = call_agent_for_plan(client, plot_prompt, plot_context, story_id, log_type="prism_devise_plot")
    plan_dict["Key Plot Points"] = plot_output

    # Prism calibration (max 1 iteration)
    spectrum_dimensions = ["Story Structure", "Originality", "Depth", "Style", "Task Alignment"]
    need_refine = False

    # Beam Focusing phase
    beam_focusing_prompt = (
        "Perform Beam Focusing: produce a compact, beam-focused summary of the current plan elements (Central Conflict, Character Descriptions, Setting, Key Plot Points). "
        "Focus on the essential information needed to support downstream spectrum analysis and generation. Keep it concise but retain details required for expansive story generation. Output a compact summary for subsequent agents."
    )
    beam_focusing_context = f"Original Task: {creative_writing_task}\n\nCurrent Plan: {json.dumps(plan_dict, ensure_ascii=False)}"
    beam_focusing_output = call_agent_for_plan(client, beam_focusing_prompt, beam_focusing_context, story_id, log_type="prism_beam_focusing")

    # Spectrum Conference (single-round debate)
    spectrum_conf_prompt = (
        "Initiate a Spectrum Conference: based on the beam-focused summary, run a single-round multi-agent collaborative discussion. "
        "Assign adaptive roles: Coherence Coordinator (structure), Innovator (originality), Expander (depth), Stylist (style). "
        "Agents should exchange ideas synergistically: propose improvements, briefly reflect on others' points, and build toward unified suggestions. "
        "Produce a transcript (more than 10 exchanges) and conclude with consolidated, actionable suggestions aligned with the original task."
    )
    spectrum_conf_context = f"Original Task: {creative_writing_task}\n\nBeam Focused Summary: {beam_focusing_output}"
    spectrum_conf_output = call_agent_for_plan(client, spectrum_conf_prompt, spectrum_conf_context, story_id, log_type="prism_spectrum_conference")

    # Spectral Analysis (parallel critiques)
    spectral_critiques = ""
    grades = []
    grade_map = {"A": 3, "B": 2, "C": 1}
    for dim in spectrum_dimensions:
        spectral_prompt = (
            f"Perform Spectral Analysis for one spectrum band: {dim}. "
            f"For the {dim} Analyst: provide an assessment (grade A/B/C with evidence) focused on {'coherence, consistency, and progression' if dim=='Story Structure' else 'innovation and avoidance of clichés' if dim=='Originality' else 'character/setting richness and believability' if dim=='Depth' else 'variety, devices, and expressiveness' if dim=='Style' else 'adherence to the original task (key elements, perspective, implications)'}."
            " Start with Grade: X\nThen provide bullet-pointed suggestions."
        )
        spectral_context = f"Original Task: {creative_writing_task}\n\nBeam Focused Summary: {beam_focusing_output}\n\nSpectrum Conference Transcript: {spectrum_conf_output}"
        spectral_output = call_agent_for_plan(client, spectral_prompt, spectral_context, story_id, log_type=f"prism_spectral_analysis_{dim}")
        spectral_critiques += f"\n{dim} Spectral Analysis:\n{spectral_output}"
        grade_match = re.search(r'Grade: (A|B|C)', spectral_output, re.IGNORECASE)
        if grade_match:
            grade = grade_match.group(1).upper()
            grades.append(grade_map.get(grade, 0))

    # Focal Decision phase
    focal_decision_prompt = (
        "Conduct a Focal Decision: given the spectral analyses, determine revision category. Compute average grade (or majority). "
        "Output category as one of: 'Severe (majority C)' / 'Major (majority B)' / 'Minor (majority A with B)' / 'No Issue (all A)'. "
        "Provide reasons and confidence (High/Medium/Low). If category is below B, list targeted fixes."
    )
    focal_decision_context = f"Spectral Analyses: {spectral_critiques}"
    focal_decision_output = call_agent_for_plan(client, focal_decision_prompt, focal_decision_context, story_id, log_type="prism_focal_decision")

    category_match = re.search(r'category: \'(Severe|Major|Minor|No Issue)\'', focal_decision_output, re.IGNORECASE)
    if category_match:
        category = category_match.group(1).upper()
        if category in ['SEVERE', 'MAJOR']:
            need_refine = True
            suggestions = re.search(r'suggest targeted fixes:\s*(.*)', focal_decision_output, re.DOTALL | re.IGNORECASE)
            refine_suggestions = suggestions.group(1).strip() if suggestions else ""
        else:
            need_refine = False
            refine_suggestions = ""
    else:
        need_refine = True
        refine_suggestions = ""

    # Beam Reforging (refine if needed)
    if need_refine:
        beam_reforge_prompt = (
            "Perform Beam Reforging: based on the beam-focused summary, spectral analyses, and focal decision suggestions, refine each plan element (Central Conflict, Character Descriptions, Setting, Key Plot Points). "
            "Produce detailed, expanded refinements that support longer story generation. Output in exact format:\n"
            "Central Conflict: <refined text>\nCharacter Descriptions: <refined text>\nSetting: <refined text>\nKey Plot Points: <refined text>\n"
            "Ensure refinements enhance all relevant spectrum dimensions and strictly follow the original task."
        )
        beam_reforge_context = f"Original Task: {creative_writing_task}\n\nBeam Focused Summary: {beam_focusing_output}\n\nFocal Decision Suggestions: {refine_suggestions}\n\nSpectral Analyses: {spectral_critiques}\n\nSpectrum Conference: {spectrum_conf_output}"
        beam_reforge_output = call_agent_for_plan(client, beam_reforge_prompt, beam_reforge_context, story_id, log_type="prism_beam_reforging")

        refined_conflict_match = re.search(r'Central Conflict\s*:\s*(.*?)(?=\s*Character Descriptions\s*:|\Z)', beam_reforge_output, re.DOTALL | re.IGNORECASE)
        refined_character_match = re.search(r'Character Descriptions\s*:\s*(.*?)(?=\s*Setting\s*:|\Z)', beam_reforge_output, re.DOTALL | re.IGNORECASE)
        refined_setting_match = re.search(r'Setting\s*:\s*(.*?)(?=\s*Key Plot Points\s*:|\Z)', beam_reforge_output, re.DOTALL | re.IGNORECASE)
        refined_plot_match = re.search(r'Key Plot Points\s*:\s*(.*)', beam_reforge_output, re.DOTALL | re.IGNORECASE)

        if refined_conflict_match and refined_character_match and refined_setting_match and refined_plot_match:
            plan_dict["Central Conflict"] = refined_conflict_match.group(1).strip()
            plan_dict["Character Descriptions"] = refined_character_match.group(1).strip()
            plan_dict["Setting"] = refined_setting_match.group(1).strip()
            plan_dict["Key Plot Points"] = refined_plot_match.group(1).strip()
        else:
            print(f"[WARN] Beam Reforging parse failed. Keeping current plan_dict.")
            retry_reforge_prompt = beam_reforge_prompt + " Strictly follow the exact output keys and format."
            retry_reforge_output = call_agent_for_plan(client, retry_reforge_prompt, beam_reforge_context, story_id, log_type="prism_beam_reforging_retry")
            retry_conflict_match = re.search(r'Central Conflict\s*:\s*(.*?)(?=\s*Character Descriptions\s*:|\Z)', retry_reforge_output, re.DOTALL | re.IGNORECASE)
            retry_character_match = re.search(r'Character Descriptions\s*:\s*(.*?)(?=\s*Setting\s*:|\Z)', retry_reforge_output, re.DOTALL | re.IGNORECASE)
            retry_setting_match = re.search(r'Setting\s*:\s*(.*?)(?=\s*Key Plot Points\s*:|\Z)', retry_reforge_output, re.DOTALL | re.IGNORECASE)
            retry_plot_match = re.search(r'Key Plot Points\s*:\s*(.*)', retry_reforge_output, re.DOTALL | re.IGNORECASE)
            if retry_conflict_match and retry_character_match and retry_setting_match and retry_plot_match:
                plan_dict["Central Conflict"] = retry_conflict_match.group(1).strip()
                plan_dict["Character Descriptions"] = retry_character_match.group(1).strip()
                plan_dict["Setting"] = retry_setting_match.group(1).strip()
                plan_dict["Key Plot Points"] = retry_plot_match.group(1).strip()
            else:
                print(f"[WARN] Beam Reforging retry failed. Keeping current plan_dict.")

    return plan_dict

# -------------------------
# main(...) to support batch_runner call
# returns dict for upstream saving
# supports various parameter names
# -------------------------
def main(example_id=None, story_id=None, creative_input=None, task=None, output_dir=None, plan_output_file=None, plan_file=None):
    sid = example_id or story_id or "example_unknown"
    creative = creative_input or task or ""
    plan_path = plan_output_file or plan_file
    if not plan_path and output_dir:
        plan_path = os.path.join(output_dir, "story_plan.json")

    plan_dict = generate_plan_only(sid, creative)
    result = {"plan": plan_dict, "example_id": sid}

    if plan_path:
        try:
            os.makedirs(os.path.dirname(plan_path), exist_ok=True)
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"[INFO] Plan written to {plan_path}")
        except Exception as e:
            print(f"[WARN] cannot write plan to {plan_path}: {e}")

    return result

# -------------------------
# CLI entry for subprocess fallback
# -------------------------
if __name__ == "__main__":
    sid = os.environ.get("STORY_ID", os.environ.get("example_id", "example_unknown"))
    task = os.environ.get("TASK", os.environ.get("creative_input", ""))
    outdir = os.environ.get("OUTPUT_DIR", None)
    plan_out = None
    if outdir:
        try:
            os.makedirs(outdir, exist_ok=True)
            plan_out = os.path.join(outdir, "story_plan.json")
        except Exception:
            plan_out = None

    main(example_id=sid, creative_input=task, output_dir=outdir, plan_output_file=plan_out)
