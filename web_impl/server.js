import express from "express";
import path from "path";
import { fileURLToPath } from "url";
import {
  LambdaClient,
  InvokeCommand,
  GetFunctionCommand,
} from "@aws-sdk/client-lambda";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

const PORT = 3000;

const LAMBDA_ENDPOINT = "http://localhost:4566";
const AWS_REGION = "us-east-1";
const BASELINE_FUNCTION_NAME = "stress-test-baseline";
const SHM_FUNCTION_NAME = "stress-test-shm";

const lambdaClient = new LambdaClient({
  region: AWS_REGION,
  endpoint: LAMBDA_ENDPOINT,
  credentials: {
    accessKeyId: "test",
    secretAccessKey: "test",
  },
});

function safeJsonParse(text) {
  if (text == null) return null;
  const trimmed = String(text).trim();
  if (!trimmed) return null;

  try {
    return JSON.parse(trimmed);
  } catch {
    return null;
  }
}

function parseLambdaPayload(payloadUint8Array) {
  const rawText = payloadUint8Array
    ? Buffer.from(payloadUint8Array).toString("utf-8").trim()
    : "";

  if (!rawText) return {};

  const parsed = safeJsonParse(rawText);

  if (parsed === null) {
    return { raw_response: rawText };
  }

  if (typeof parsed === "object" && parsed !== null && "body" in parsed) {
    const body = parsed.body;
    if (typeof body === "string") {
      const parsedBody = safeJsonParse(body);
      return parsedBody ?? { body };
    }
    return body ?? {};
  }

  return parsed;
}

async function checkFunctionExists(functionName) {
  try {
    await lambdaClient.send(
      new GetFunctionCommand({ FunctionName: functionName })
    );
    return { ok: true, error: null };
  } catch (err) {
    return { ok: false, error: err.message || String(err) };
  }
}

async function invokeSingleLambda(functionName, seriesName, invokeType) {
  const payload = {
    Records: [
      {
        s3: {
          bucket: { name: "demo-web-bucket" },
          object: { key: "dummy_50mb.txt" },
        },
      },
    ],
  };

  const start = performance.now();

  try {
    const response = await lambdaClient.send(
      new InvokeCommand({
        FunctionName: functionName,
        InvocationType: "RequestResponse",
        Payload: Buffer.from(JSON.stringify(payload)),
      })
    );

    const end = performance.now();
    const latencyMs = end - start;

    const functionError = response.FunctionError || null;
    const parsedResult = parseLambdaPayload(response.Payload);

    if (functionError) {
      return {
        success: false,
        series: seriesName,
        function_name: functionName,
        error: `Lambda error: ${functionError}`,
        latency_ms: latencyMs,
        result: parsedResult,
      };
    }

    return {
      success: true,
      series: seriesName,
      function_name: functionName,
      error: null,
      latency_ms: latencyMs,
      result: parsedResult,
    };
  } catch (err) {
    return {
      success: false,
      series: seriesName,
      function_name: functionName,
      error: `Invoke error: ${err.message || String(err)}`,
      latency_ms: 0,
      result: {},
    };
  }
}

app.get("/api/health", (_req, res) => {
  res.json({ ok: true });
});

app.post("/api/invoke-batch", async (req, res) => {
  const count = Number(req.body?.count ?? 100);
  const invokeType = req.body?.invokeType || "Warm Start";

  const [baselineExists, shmExists] = await Promise.all([
    checkFunctionExists(BASELINE_FUNCTION_NAME),
    checkFunctionExists(SHM_FUNCTION_NAME),
  ]);

  if (!baselineExists.ok) {
    return res.status(400).json({
      error: `Function '${BASELINE_FUNCTION_NAME}' not found. ${baselineExists.error}`,
    });
  }

  if (!shmExists.ok) {
    return res.status(400).json({
      error: `Function '${SHM_FUNCTION_NAME}' not found. ${shmExists.error}`,
    });
  }

  let finalBaseline = null;
  let finalShm = null;

  try {
    for (let i = 0; i < count; i++) {
      // Faster than sequential per cycle:
      // Baseline + eBPF run at the same time for each internal cycle
      const [baseline, shm] = await Promise.all([
        invokeSingleLambda(BASELINE_FUNCTION_NAME, "Baseline", invokeType),
        invokeSingleLambda(SHM_FUNCTION_NAME, "eBPF / Zero-Copy", invokeType),
      ]);

      finalBaseline = baseline;
      finalShm = shm;
    }

    return res.json({
      baseline: finalBaseline,
      shm: finalShm,
      timestamp: new Date().toISOString(),
      internalCount: count,
    });
  } catch (err) {
    return res.status(500).json({
      error: err.message || String(err),
    });
  }
});

app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
