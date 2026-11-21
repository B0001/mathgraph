/-
Template for the kernel-certified relabel audit (mathgraph-6vm).

`mathgraph/kaudit.py` writes batch files that are this file followed by
generated commands, and runs each one from inside the mathlib4 checkout built
at the index pin, the way DumpDecls.lean is run:

    cd mathlib4 && lake env lean /path/to/batch.lean

Nothing is written into the checkout. The generated commands are:

* `#kresolve "names.tsv" "facts.jsonl"`. For every `name<TAB>module` line it
  records whether the name is a constant (or a private one of that module),
  plus its kind, `[simp]` status, deprecation, `to_additive` translation and
  pretty-printed type.
* One check per line: `attribute [-simp] H T in theorem kaudit.cN : type_of% @H
  := by intros; first | kalt "K1" (tac) | ...`. On the next line,
  `#kdump kaudit.cN` records the constants that the finished proof term uses.
  - A failed tactic block leaves the theorem in place, proved by `sorryAx`
    (error recovery).
  - A statement that does not elaborate leaves no theorem at all.
  - A theorem that is added has been through `addDecl`, so the kernel has
    checked its proof.

`kalt` and `#kdump` append JSON lines to `<batch file>.kdump.jsonl` and flush
each one. So when a batch dies, every result before the crash survives, and
the first check without a line is the one that killed it.
-/

import Mathlib

open Lean Elab Command Meta

-- `#kdump` has to see finished proofs, not pending async elaboration tasks.
set_option Elab.async false
set_option autoImplicit false
set_option linter.all false

def kauditKind : ConstantInfo → String
  | .thmInfo _ => "theorem"
  | .defnInfo _ => "def"
  | .axiomInfo _ => "axiom"
  | .inductInfo _ => "inductive"
  | .ctorInfo _ => "ctor"
  | .opaqueInfo _ => "opaque"
  | .recInfo _ => "rec"
  | .quotInfo _ => "quot"

/-- Append `j` to `<this file>.kdump.jsonl` and flush it. -/
def kauditWrite (file : String) (j : Json) : IO Unit := do
  let h ← IO.FS.Handle.mk (file ++ ".kdump.jsonl") .append
  h.putStrLn j.compress
  h.flush

open Tactic in
/-- `kalt "K1" tac` runs `tac` and succeeds only if `tac` closed the main goal
with a complete term. That means no goals left, no unassigned holes and no
`sorry`. Then it records the tag.

Some tactics succeed while leaving holes behind. `simpa ... using T ..` is one,
and the theorem would then fail only at its end. Without this check, `first`
commits to such an alternative and never tries the later ones. -/
elab "kalt " s:str t:tactic : tactic => do
  let g ← getMainGoal
  evalTactic t
  Term.synthesizeSyntheticMVarsNoPostponing
  unless (← getUnsolvedGoals).isEmpty do throwError "kalt: goals remain"
  let pf ← instantiateMVars (.mvar g)
  if pf.hasExprMVar then throwError "kalt: unassigned holes"
  if pf.hasSorry then throwError "kalt: sorry"
  kauditWrite (← getFileName) (Json.mkObj [("tag", toJson s.getString)])

/-- One JSON line: the constants that the value of `n` uses. -/
elab "#kdump " id:ident : command => do
  let n := id.getId
  let ci? : Option ConstantInfo := (← getEnv).find? n
  let obj := match ci? with
    | none => Json.mkObj [("kdump", toJson n.toString), ("absent", toJson true)]
    | some ci =>
      let used : Array Name := match ci.value? (allowOpaque := true) with
        | some v => v.getUsedConstants
        | none => #[]
      let names : Array String := used.map fun c : Name => c.toString
      Json.mkObj [("kdump", toJson n.toString), ("used", toJson names)]
  kauditWrite (← getFileName) (obj.setObjVal! "ms" (toJson (← IO.monoMsNow)))

/-- Facts about every `name<TAB>module` line of `inp`, one JSON line each. -/
elab "#kresolve " inp:str out:str : command => liftTermElabM do
  let env ← getEnv
  let simp ← getSimpTheorems
  let h ← IO.FS.Handle.mk out.getString .write
  for line in ← IO.FS.lines inp.getString do
    let [name, mod] := line.splitOn "\t" | continue
    let n := name.toName
    let priv := mkPrivateNameCore mod.toName n
    let c? := if env.contains n then some n else if env.contains priv then some priv else none
    let mut fields : List (String × Json) := [("name", toJson name)]
    if let some c := c? then
      let ci ← getConstInfo c
      let ty ← withOptions (fun o => o.set `format.width (10000 : Nat)) (ppExpr ci.type)
      let add := Mathlib.Tactic.Translate.findTranslationName? env Mathlib.Tactic.ToAdditive.data c
      fields := fields ++ [
        ("const", toJson c.toString),
        ("private", toJson (c != n)),
        ("kind", toJson (kauditKind ci)),
        ("simp", toJson (simp.isLemma (.decl c))),
        ("deprecated", toJson (Linter.isDeprecated env c)),
        ("new_name", toJson ((Linter.getDeprecatedNewName env c).map (·.toString))),
        ("additive", toJson (add.map (·.toString))),
        ("type", toJson ((toString ty).replace "\n" " "))]
    h.putStrLn (Json.mkObj fields).compress
  h.flush
