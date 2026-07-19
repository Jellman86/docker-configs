FROM nousresearch/hermes-agent:v2026.7.7.2@sha256:9c841866021c54c4596849f6135717e8a4d52ba510b7f52c50aef1de1a283973

# Hermes intentionally keeps /opt/hermes immutable at runtime. Install the
# selected memory provider into the image, verifying the exact PyPI artifact.
RUN set -eux; \
    wheel=/tmp/honcho_ai-2.2.0-py3-none-any.whl; \
    curl -fsSL \
      https://files.pythonhosted.org/packages/d0/c6/66af5f7ba3d75796f4523eac1e069fbdc759c3f0b8adab9fb7ae04e15784/honcho_ai-2.2.0-py3-none-any.whl \
      -o "$wheel"; \
    echo "32f098a4c8bcfe4288f0994ddab0bc52a68dc87069d0f2ce2c8758ee2a1761f2  $wheel" | sha256sum -c -; \
    uv pip install --python /opt/hermes/.venv/bin/python --no-deps "$wheel"; \
    /opt/hermes/.venv/bin/python -c \
      "from importlib.metadata import version; assert version('honcho-ai') == '2.2.0'; from honcho import Honcho"; \
    rm -f "$wheel"
