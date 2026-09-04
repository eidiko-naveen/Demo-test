import json
import re
from services.llm_interface import LLMInterface
from models.config import AgentSpec, ModelConfig

BUILDER_MODEL = "gemini-3.5-flash-lite"

BUILDER_SYSTEM_PROMPT = """
You are an expert AI Agent Designer.
Your job is to take a user's requirement and generate a complete Agent Specification in JSON format.

You must return ONLY a valid JSON object with this exact structure:
{
    "name": "Agent Name",
    "description": "What this agent does",
    "capabilities": ["capability1", "capability2"],
    "tools": [],
    "input_schema": {
        "field_name": "field_type"
    },
    "output_schema": {
        "field_name": "field_type"
    },
    "system_prompt": "Detailed system prompt for this agent"
}

Rules:
1. name must be short and descriptive ending with Agent
2. capabilities must be a list of strings describing what the agent can do
3. system_prompt must be detailed and specific to the agent's purpose
4. input_schema and output_schema must reflect the agent's expected inputs and outputs
5. Return ONLY the JSON object, no explanation, no markdown, no code blocks
"""


class BuilderService:
    def __init__(self):
        self.llm = LLMInterface()

    def build_agent(
        self,
        user_prompt: str,
        provider: str = "gemini",
        model: str = "gemini-3.5-flash-lite"
    ) -> AgentSpec:
        try:
            raw_response = self.llm.generate_with_system_prompt(
                system_prompt=BUILDER_SYSTEM_PROMPT,
                user_input=user_prompt,
                model_name=BUILDER_MODEL
            )

            cleaned = self._clean_response(raw_response)
            spec_dict = json.loads(cleaned)

            spec = AgentSpec(
                name=spec_dict.get("name", "Unnamed Agent"),
                description=spec_dict.get("description", ""),
                capabilities=spec_dict.get("capabilities", []),
                tools=spec_dict.get("tools", []),
                model=ModelConfig(
                    provider=provider,
                    model=model
                ),
                input_schema=spec_dict.get("input_schema", {}),
                output_schema=spec_dict.get("output_schema", {}),
                system_prompt=spec_dict.get("system_prompt", "")
            )
            return spec

        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse agent specification: {str(e)}")
        except Exception as e:
            raise Exception(f"Agent Builder failed: {str(e)}")

    def _clean_response(self, response: str) -> str:
        cleaned = response.strip()
        cleaned = re.sub(r'^```json\s*', '', cleaned)
        cleaned = re.sub(r'^```\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
        return cleaned.strip()