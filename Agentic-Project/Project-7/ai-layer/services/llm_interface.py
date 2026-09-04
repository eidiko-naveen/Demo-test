from services.gemini_service import GeminiService


class LLMInterface:
    def __init__(self):
        self.gemini = GeminiService()
        self.default_model = "gemini-3.5-flash-lite"

    def generate(self, prompt: str, model_name: str = None) -> str:
        model = model_name or self.default_model
        return self.gemini.generate_text(prompt, model)

    def generate_with_system_prompt(
        self,
        system_prompt: str,
        user_input: str,
        model_name: str = None
    ) -> str:
        model = model_name or self.default_model
        return self.gemini.generate_with_system_prompt(
            system_prompt,
            user_input,
            model
        )