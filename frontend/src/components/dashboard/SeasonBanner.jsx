const SeasonBanner = ({ season = '2024', isLive = false }) => {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-dirt bg-chalk text-xs font-mono w-fit">
      {isLive ? (
        <>
          {/* Pulsing green dot for live season */}
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-pine opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-pine" />
          </span>
          <span className="text-chalk200 tracking-widest uppercase">
            Live — {season} Season
          </span>
        </>
      ) : (
        <>
          {/* Static amber dot for historical snapshot */}
          <span className="h-2 w-2 rounded-full bg-amber opacity-80" />
          <span className="text-chalk400 tracking-widest uppercase">
            {season} End-of-Season Snapshot
          </span>
        </>
      )}
    </div>
  );
};

export default SeasonBanner;