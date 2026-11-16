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

  return (
    <header className="sticky top-0 z-40 px-4 sm:px-6 lg:px-8 pt-3 pb-2">
      <div className="w-full max-w-[1600px] mx-auto glass-panel-elevated rounded-2xl px-6 sm:px-8 h-16 flex md:grid md:grid-cols-[1fr_auto_1fr] items-center justify-between gap-6">
        {/* Brand Wordmark fusing Rhodes Cyan + Endfield Volt */}
        <button
          type="button"
          onClick={() => onNavigate('qa')}
          className="flex items-center gap-3 text-left whitespace-nowrap shrink-0 justify-self-start focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#17D1FF] rounded-md cursor-pointer"
        >
          <svg
            width="30"
            height="30"
            viewBox="0 0 30 30"
            fill="none"
            aria-hidden="true"
            className="shrink-0"
          >
            <polygon
              points="15,2 28,15 15,28 2,15"
              stroke="#18181B"
              strokeWidth="1.6"
              fill="#FFFFFF"
            />
            <polygon points="15,6 15,24 6,15" fill="#17D1FF" fillOpacity="0.88" />
            <polygon points="15,6 24,15 15,24" fill="#FFE600" fillOpacity="0.92" />
            <polygon points="15,11 19,15 15,19 11,15" fill="#18181B" />
          </svg>
          <span className="text-[17px] font-semibold tracking-tight text-slate-950">
            PRTS · 终末地攻略库
          </span>
        </button>

        {/* Centered Compact Navigation Tabs */}
        <nav
          className="hidden md:flex items-center justify-center gap-4 lg:gap-6"
          aria-label="主导航"
        >
          {navItems.map((item) => {
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onNavigate(item.id)}
                className="group relative px-3.5 py-2 text-sm transition-colors duration-150 whitespace-nowrap shrink-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#17D1FF] rounded-sm"
              >
                <span className="inline-grid place-items-center">
                  <span
                    className={`col-start-1 row-start-1 ${
                      isActive
                        ? 'font-semibold text-slate-950'
                        : 'font-medium text-slate-600 group-hover:text-slate-950'
                    }`}
                  >
                    {item.label}
                  </span>
                  <span
                    aria-hidden="true"
                    className="col-start-1 row-start-1 invisible font-semibold select-none"
                  >
                    {item.label}
                  </span>
                </span>
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute left-1.5 right-1.5 -bottom-0.5 h-[2.5px] dual-spectrum-line rounded-full"
                  />
                )}
              </button>
            );
          })}
        </nav>

        {/* Right Balance Spacer for True Center Alignment */}
        <div className="hidden md:block" aria-hidden="true" />
      </div>

      {/* Mobile Compact Navigation Bar */}
      <nav
        className="md:hidden mt-2 max-w-[1600px] mx-auto glass-panel rounded-xl p-1 flex items-center justify-between gap-1"
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
