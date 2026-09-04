import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()


class GeminiService:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        genai.configure(api_key=api_key)

    def get_model(self, model_name: str = "gemini-3.5-flash-lite"):
        return genai.GenerativeModel(model_name)

    def generate_text(self, prompt: str, model_name: str = "gemini-3.5-flash-lite") -> str:
        try:
            model = self.get_model(model_name)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Gemini generation failed: {str(e)}")

    def generate_with_system_prompt(
        self,
        system_prompt: str,
        user_input: str,
        model_name: str = "gemini-1.5-flash"
    ) -> str:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_prompt
            )
            response = model.generate_content(user_input)
            return response.text
        except Exception as e:
            raise Exception(f"Gemini generation failed: {str(e)}")