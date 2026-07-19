/** Fixed ambient aurora background — pure CSS animation, honors reduced motion. */
export default function Aurora() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-0 bg-grid" />
      <div
        className="aurora-blob left-[-10%] top-[-20%] h-[45vh] w-[45vw]"
        style={{ background: "#6a4eff" }}
      />
      <div
        className="aurora-blob right-[-15%] top-[10%] h-[40vh] w-[38vw]"
        style={{ background: "#e89c30", animationDelay: "-8s", opacity: 0.07 }}
      />
      <div
        className="aurora-blob bottom-[-25%] left-[25%] h-[40vh] w-[42vw]"
        style={{ background: "#a391ff", animationDelay: "-16s", opacity: 0.08 }}
      />
    </div>
  );
}
