// ABOUTME: Test-only loader for the API fixtures recorded by the Python suite
// ABOUTME: Validates each fixture against the same JSON Schema the server side asserts against

import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// the 2020 build, because the schemas declare draft 2020-12 - ajv's default
// export only knows draft-07 and fails to resolve the $schema
import Ajv from "ajv/dist/2020.js";

const backendDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const FIXTURE_DIR = resolve(backendDir, "tests/fixtures/json_api");
const SCHEMA_DIR = resolve(backendDir, "src/opendlp/schemas/json_api");

const ajv = new Ajv({ allErrors: true });

// ajv registers a schema under its $id on compile and refuses to see the same one
// twice, so compiled validators are reused rather than rebuilt per call.
const validators = new Map();

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function validatorFor(schemaName) {
  if (!validators.has(schemaName)) {
    const schema = readJson(resolve(SCHEMA_DIR, `${schemaName}.schema.json`));
    validators.set(schemaName, ajv.compile(schema));
  }
  return validators.get(schemaName);
}

/**
 * List the recorded API fixtures, by name.
 *
 * @returns {string[]} fixture names, without the .json suffix
 */
export function fixtureNames() {
  return readdirSync(FIXTURE_DIR)
    .filter((entry) => entry.endsWith(".json"))
    .map((entry) => entry.replace(/\.json$/, ""));
}

/**
 * Load a recorded API response and check it against its schema.
 *
 * A JS test must never hand-type an API payload: a literal only records what the
 * author believed the server returns, and nothing makes it wrong when the server
 * changes. A fixture is a real response, re-recorded by the Python suite, which
 * fails if it drifts.
 *
 * @param {string} name - fixture file name, without the .json suffix
 * @param {string} schemaName - schema file name, without the .schema.json suffix
 * @returns {Object} the parsed fixture
 * @throws {Error} if the fixture does not validate against the schema
 */
export function loadApiFixture(name, schemaName) {
  const fixture = readJson(resolve(FIXTURE_DIR, `${name}.json`));

  const validate = validatorFor(schemaName);
  if (!validate(fixture)) {
    throw new Error(
      `API fixture "${name}" does not match schema "${schemaName}": ` +
        ajv.errorsText(validate.errors),
    );
  }
  return fixture;
}
