// Context propagation, the contract of the platform's routing (ADR 0035).
//
// A route by baggage (`platform workload route --baggage sandbox=pr-42`) only holds past the first call if
// every service passes the baggage header on: the mesh does not link an incoming request to the calls it
// makes. Node has no implicit context, so this module wires it: AsyncLocalStorage carries the context
// through the request's async work, the http instrumentation reads traceparent and baggage from each
// incoming request, and the undici instrumentation writes them into every fetch() made from it. Call other
// services with fetch() and the chain keeps its baggage; never copy headers by hand.
//
// Only the OpenTelemetry API: propagation needs no SDK and no exporter. Load this module before anything
// that requires http (src/app.js does it on its first line).
const { context, propagation } = require('@opentelemetry/api');
const { AsyncLocalStorageContextManager } = require('@opentelemetry/context-async-hooks');
const { CompositePropagator, W3CBaggagePropagator, W3CTraceContextPropagator } = require('@opentelemetry/core');
const { registerInstrumentations } = require('@opentelemetry/instrumentation');
const { HttpInstrumentation } = require('@opentelemetry/instrumentation-http');
const { UndiciInstrumentation } = require('@opentelemetry/instrumentation-undici');

context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());
propagation.setGlobalPropagator(
  new CompositePropagator({ propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()] }),
);
registerInstrumentations({ instrumentations: [new HttpInstrumentation(), new UndiciInstrumentation()] });
