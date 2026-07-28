/-
Dump every declaration's *elaborated* type from a built Mathlib.

Run from inside a mathlib4 checkout that has been built (`lake exe cache get`
then `lake build`):

    cp DumpDecls.lean mathlib4/DumpDecls.lean
    cd mathlib4 && lake env lean DumpDecls.lean

Writes `decls_elab.jsonl` in the working directory, one object per line:
`{"name": ..., "module": ..., "type": ...}` where `type` is the
pretty-printed, typeclass-resolved, notation-expanded statement.

This is the input the structural matchers actually want. Everything upstream
of it scrapes types out of source text with regexes, which loses exactly the
information that elaboration adds: implicit arguments made explicit, notation
resolved to its underlying constant, and the ~14k declarations that
`@[to_additive]` generates and never writes to source appearing as
first-class entries with real types rather than reconstructed names.

The work runs at elaboration time via `run_cmd`, so the environment is
already populated by the `import Mathlib` above -- no manual `importModules`,
no search-path juggling.
-/

import Mathlib
import Lean

open Lean Elab Command Meta

/-- Names that exist only as compiler artifacts and carry no mathematical
content: equation lemmas, match auxiliaries, projections, and the like. -/
def isNoise (n : Name) : Bool :=
  n.isInternal
    || n.isAnonymous
    || (`_example).isPrefixOf n
    || n.components.any fun c =>
         let s := c.toString
         s.startsWith "_" || s == "proof" || s == "eq_def"
         || s.startsWith "match_" || s.startsWith "eq_" && s.length > 3
           && (s.drop 3).all Char.isDigit

run_cmd liftTermElabM do
  let env ← getEnv
  let h ← IO.FS.Handle.mk "decls_elab.jsonl" IO.FS.Mode.write
  let mut written : Nat := 0
  let mut skipped : Nat := 0
  for (name, info) in env.constants.toList do
    if isNoise name then
      skipped := skipped + 1
      continue
    let some modIdx := env.getModuleIdxFor? name | continue
    let modName := env.header.moduleNames[modIdx.toNat]!
    -- Pretty-print without the width-based line breaking: the matchers read
    -- the type as a single string and inserted newlines only add noise.
    let fmt ← withOptions (fun o =>
        (o.setNat `format.width 10000).setBool `pp.unicode.fun true) do
      ppExpr info.type
    let typeStr := (toString fmt).replace "\n" " "
    let obj := Json.mkObj [
      ("name", Json.str name.toString),
      ("module", Json.str modName.toString),
      ("kind", Json.str (match info with
        | .thmInfo _ => "theorem"
        | .defnInfo _ => "def"
        | .axiomInfo _ => "axiom"
        | .inductInfo _ => "inductive"
        | .ctorInfo _ => "ctor"
        | .opaqueInfo _ => "opaque"
        | .recInfo _ => "rec"
        | .quotInfo _ => "quot")),
      ("type", Json.str typeStr)]
    h.putStrLn obj.compress
    written := written + 1
  h.flush
  logInfo m!"wrote {written} declarations to decls_elab.jsonl (skipped {skipped})"
