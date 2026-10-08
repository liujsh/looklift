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
  definitions.length < 1 ||
  definitions.length > 32 ||
  new Set(definitions.map((item) => item?.name)).size !== definitions.length ||
  definitions.some(
    (item) =>
      !item ||
      typeof item.name !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(item.name) ||
      typeof item.description !== "string" ||
      !item.inputSchema ||
      item.inputSchema.type !== "object"
  )
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
          terminate: definition.terminal === true && value.result.ok === true,
        };
      },
    });
  }
}
