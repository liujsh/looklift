import { readFileSync } from "node:fs";

const gatewayUrl = process.env.LOOKLIFT_GATEWAY_URL;
const token = process.env.LOOKLIFT_TOOL_TOKEN;
const schemaFile = process.env.LOOKLIFT_TOOL_SCHEMA_FILE;

if (!gatewayUrl || !token || !schemaFile) {
  throw new Error("LookLift Tool Gateway 配置不完整");
}

const definitions = JSON.parse(readFileSync(schemaFile, "utf8"));
if (
  !Array.isArray(definitions) ||
  definitions.length !== 2 ||
  definitions.some((item) => !["render_candidate", "finish_candidate"].includes(item.name))
) {
  throw new Error("LookLift Tool Schema 不合法");
}

async function callGateway(name, params, signal) {
  const response = await fetch(`${gatewayUrl}/tools/${name}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(params),
    signal,
  });
  if (!response.ok) {
    throw new Error("LookLift Tool Gateway 调用失败");
  }
  return response.json();
}

export default function (pi) {
  for (const definition of definitions) {
    pi.registerTool({
      name: definition.name,
      label: definition.name,
      description: definition.description,
      parameters: definition.inputSchema,
      async execute(_toolCallId, params, signal) {
        const value = await callGateway(definition.name, params, signal);
        const content = [{ type: "text", text: JSON.stringify(value.result) }];
        if (value.preview_base64) {
          content.push({
            type: "image",
            data: value.preview_base64,
            mimeType: "image/jpeg",
          });
        }
        return {
          content,
          details: value.result,
          terminate: definition.name === "finish_candidate" && value.result.ok === true,
        };
      },
    });
  }
}
