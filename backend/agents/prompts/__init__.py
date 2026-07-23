# -*- coding: utf-8 -*-
"""ADR-0003：业务 prompt 集中到 git 文件库（backend/agents/prompts/*.md）。"""
from agents.prompts.loader import load_prompt, prompts_dir

__all__ = ["load_prompt", "prompts_dir"]
