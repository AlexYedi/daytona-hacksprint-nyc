// Publish is permitted only when the verifier found zero unsourced claims.
// Evaluated in code on the verifier's verdict JSON, never on the model's say-so.
permit (
  principal,
  action == Action::"publish",
  resource
)
when { context.unsourced_count == 0 };
