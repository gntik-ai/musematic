module.exports = {
  meta: {
    type: "problem",
    docs: {
      description: "Disallow hardcoded user-facing JSX strings outside the i18n migration allowlist.",
    },
    schema: [
      {
        type: "object",
        properties: {
          allowlist: {
            type: "array",
            items: { type: "string" },
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      hardcoded: "User-facing JSX text must be sourced through the i18n catalogue.",
    },
  },
  create(context) {
    const options = context.options[0] || {};
    const allowlist = new Set(options.allowlist || []);
    const filename = context.getFilename();
    const allowed = [...allowlist].some((entry) => filename.includes(entry));

    return {
      JSXText(node) {
        if (allowed || !node.value || !node.value.trim()) {
          return;
        }
        context.report({ node, messageId: "hardcoded" });
      },
    };
  },
};

