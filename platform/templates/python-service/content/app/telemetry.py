"""Context propagation, the contract of the platform's routing (ADR 0035).

A route by baggage (`platform workload route --baggage sandbox=pr-42`) only holds past the first call if
every service passes the baggage header on: the mesh does not link an incoming request to the calls it
makes. The FastAPI instrumentation reads traceparent and baggage from each request into the current
context, and the httpx instrumentation writes them into every call made from it. Call other services
with httpx and the chain keeps its baggage; never copy headers by hand.

Only the OpenTelemetry API: propagation needs no SDK and no exporter.
"""
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor


def instrument(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)
    if not HTTPXClientInstrumentor().is_instrumented_by_opentelemetry:
        HTTPXClientInstrumentor().instrument()
