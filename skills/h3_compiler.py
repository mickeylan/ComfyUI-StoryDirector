import re


def _field(text, name):
    match = re.search(rf"(?ims)^\s*{re.escape(name)}\s*:\s*(.*?)(?=^\s*[a-z_]+\s*:|\Z)", str(text or ""))
    return match.group(1).strip() if match else ""


def compile(plan, mode="ref2va", duration=8.0):
    global_prompt = str(plan.get("global_prompt") or "").strip()
    soundscape = str(plan.get("overall_soundscape") or "").strip()
    music = str(plan.get("non_diegetic_music") or "N/A").strip() or "N/A"
    descriptions = []
    for index, segment in enumerate(plan.get("segments") or (), 1):
        prompt = str(segment.get("prompt") or "").strip()
        if not prompt:
            continue
        marker = f"[Shot {index}] "
        descriptions.append(prompt if prompt.startswith("[Shot") else marker + prompt)
    body = " ".join(descriptions)
    if str(mode).casefold() != "ref2va":
        return (f"integrated_multimodal_description: {body}\n\n"
                f"overall_soundscape: {soundscape}\n\nnon_diegetic_music: {music}")
    definitions = _field(global_prompt, "subject_definitions") or "No reusable reference subject is defined."
    retention = _field(global_prompt, "retention_analysis") or "All explicitly referenced content remains consistent wherever it appears."
    remaining = re.sub(r"(?ims)^\s*(?:subject_definitions|retention_analysis)\s*:.*?(?=^\s*[a-z_]+\s*:|\Z)", "", global_prompt).strip()
    summary = _field(global_prompt, "summary") or remaining or "[reference generation] Generate the requested target video from the supplied story and references."
    return (f"subject_definitions:\n{definitions}\n\nsummary:\n{summary}\n\n"
            f"retention_analysis:\n{retention}\n\ndetailed_description:\n{body}\n\n"
            f"overall_soundscape:\n{soundscape}\n\nnon_diegetic_music:\n{music}")
