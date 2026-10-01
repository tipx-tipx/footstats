/* układ wspólny dla 404, błędu i braku internetu: tekst po lewej, znak z logo
   po prawej (na telefonie nad tekstem), pod spodem droga dalej */
export function UkladSys({ znak, children, dol }: { znak: React.ReactNode; children: React.ReactNode; dol?: React.ReactNode }) {
  return (
    <main className="sy-sys">
      <div className="sy-sys-gora">
        <div className="sy-sys-tekst">{children}</div>
        <div className="sy-sys-znak">{znak}</div>
      </div>
      {dol}
    </main>
  );
}
