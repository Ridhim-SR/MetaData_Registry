export function BackgroundBlobs() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute z-0 h-[620px] w-[620px]"
        style={{
          left: 800,
          top: -75,
          backgroundImage:
            "radial-gradient(70.3% 70.3% at 73.27% 70.3%, #00B962 0%, #4CF371 52.23%, #FFFFFF 100%)",
          opacity: 0.5,
          filter: "blur(172px)",
        }}
      />
      <div
        className="absolute z-0 h-[600px] w-[600px] rounded-full"
        style={{
          left: -240,
          top: 600,
          opacity: 0.2,
          background:
            "radial-gradient(35.31% 35.31% at 50.07% 55.93%, #00D1FF 0%, #8AD1FF 67.36%, #FFFFFF 100%)",
          filter: "blur(80px)",
        }}
      />
      <div
        className="absolute z-0 h-[618px] w-[620px] rounded-full"
        style={{
          left: 800,
          top: 1139,
          opacity: 0.4,
          background:
            "radial-gradient(70.3% 70.3% at 73.27% 70.3%, #E7315D 0%, #FF9F8A 52.23%, #FFFFFF 100%)",
          filter: "blur(125px)",
        }}
      />
      <div
        className="absolute z-0 h-[600px] w-[700px] rounded-full"
        style={{
          left: 250,
          top: 1900,
          opacity: 0.4,
          background:
            "radial-gradient(35.31% 35.31% at 50.07% 55.93%, #FFAC00 0%, #FFD600 67.36%, #FFFFFF 100%)",
          filter: "blur(172px)",
        }}
      />
    </div>
  );
}
