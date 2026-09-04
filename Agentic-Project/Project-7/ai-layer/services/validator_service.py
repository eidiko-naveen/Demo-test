from models.config import AgentSpec


class ValidatorService:
    def validate(self, spec: AgentSpec) -> dict:
        errors = []
        warnings = []

        # Validate name
        if not spec.name or len(spec.name.strip()) == 0:
            errors.append("Agent name is required")
        elif len(spec.name) < 3:
            errors.append("Agent name must be at least 3 characters")

        # Validate description
        if not spec.description or len(spec.description.strip()) == 0:
            errors.append("Agent description is required")

        # Validate capabilities
        if not spec.capabilities or len(spec.capabilities) == 0:
            errors.append("Agent must have at least one capability")

        # Validate system prompt
        if not spec.system_prompt or len(spec.system_prompt.strip()) == 0:
            errors.append("System prompt is required")
        elif len(spec.system_prompt) < 20:
            warnings.append("System prompt is very short, consider making it more detailed")

        # Validate model
        if not spec.model:
            errors.append("Model configuration is required")
        else:
            if not spec.model.provider:
                errors.append("Model provider is required")
            if not spec.model.model:
                errors.append("Model name is required")

        # Validate input schema
        if not spec.input_schema:
            warnings.append("Input schema is empty, consider defining expected inputs")

        # Validate output schema
        if not spec.output_schema:
            warnings.append("Output schema is empty, consider defining expected outputs")

        is_valid = len(errors) == 0

        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "spec": spec.model_dump() if is_valid else None
        }