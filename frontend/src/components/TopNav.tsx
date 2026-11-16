import { PageView } from '../types/strategy';

interface TopNavProps {
  activePage: PageView;
  onNavigate: (page: PageView) => void;
}

export function TopNav({ activePage, onNavigate }: TopNavProps) {
  const navItems: { id: PageView; label: string }[] = [
    { id: 'qa', label: 'AI 战术问答' },
    { id: 'ingest', label: '添加攻略视频' },
    { id: 'library', label: '攻略切片库' },
  ];

  const primaryAction =
    activePage === 'ingest'
      ? { label: '前往 AI 问答', target: 'qa' as PageView }
      : { label: '导入攻略视频', target: 'ingest' as PageView };

  return (
    <header className="sticky top-0 z-40 px-4 sm:px-6 lg:px-8 pt-3 pb-2">
      <div className="max-w-[1360px] mx-auto glass-panel-elevated rounded-2xl px-5 sm:px-7 h-16 flex items-center justify-between gap-8">
        {/* Zone 1: Single-line Brand Wordmark */}
        <button
          type="button"
          onClick={() => onNavigate('qa')}
          className="flex items-center gap-3 text-left whitespace-nowrap shrink-0 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#17D1FF] rounded-md cursor-pointer"
        >
          <svg
            width="28"
            height="28"
            viewBox="0 0 28 28"
            fill="none"
            aria-hidden="true"
            className="shrink-0"
          >
            <polygon
              points="14,2 26,14 14,26 2,14"
              stroke="#0F172A"
              strokeWidth="1.75"
              fill="#FFFFFF"
            />
            <polygon points="14,6.5 21.5,14 14,21.5 6.5,14" fill="#17D1FF" fillOpacity="0.22" />
            <polygon points="14,9.5 18.5,14 14,18.5 9.5,14" fill="#17D1FF" />
          </svg>
          <span className="text-[17px] font-semibold tracking-tight text-slate-900">
            PRTS 战术攻略库
          </span>
        </button>

        {/* Zone 2: Clean Text Navigation Links */}
        <nav className="hidden md:flex items-center gap-8" aria-label="主导航">
          {navItems.map((item) => {
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onNavigate(item.id)}
                className={`relative py-2 text-sm font-medium transition-colors duration-150 whitespace-nowrap shrink-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#17D1FF] rounded-sm ${
                  isActive
                    ? 'text-slate-950 font-semibold'
                    : 'text-slate-600 hover:text-slate-950'
                }`}
              >
                {item.label}
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 right-0 -bottom-0.5 h-[2.5px] bg-[#17D1FF] rounded-full shadow-[0_0_10px_rgba(23,209,255,0.6)]"
                  />
                )}
              </button>
            );
          })}
        </nav>

        {/* Zone 3: Single Primary CTA */}
        <div className="flex items-center shrink-0">
          <button
            type="button"
            onClick={() => onNavigate(primaryAction.target)}
            className="ark-chamfer-sm px-4 py-2 text-[13px] font-semibold bg-[#17D1FF] text-[#071B26] hover:bg-[#33D9FF] active:scale-[0.98] transition-all duration-150 whitespace-nowrap shrink-0 cursor-pointer shadow-[0_4px_14px_rgba(23,209,255,0.32)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#008DB3]"
          >
            {primaryAction.label}
          </button>
        </div>
      </div>

      {/* Mobile Compact Navigation Bar */}
      <nav
        className="md:hidden mt-2 max-w-[1360px] mx-auto glass-panel rounded-xl p-1 flex items-center justify-between gap-1"
        aria-label="移动端导航"
      >
        {navItems.map((item) => {
          const isActive = activePage === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onNavigate(item.id)}
              className={`flex-1 py-2 px-2 text-xs font-medium rounded-lg transition-colors whitespace-nowrap truncate cursor-pointer ${
                isActive
                  ? 'bg-white text-slate-950 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </nav>
    </header>
  );
}
