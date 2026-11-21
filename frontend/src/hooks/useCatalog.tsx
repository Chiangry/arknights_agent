import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { request } from '../api/client';
import type { GameTitle, KnowledgeCategory } from '../types/strategy';

export interface CatalogGame {
  id: GameTitle;
  label: string;
  categories: { id: Exclude<KnowledgeCategory, 'all' | 'unknown'>; label: string }[];
}
const Context = createContext<{ games: CatalogGame[]; error: string }>({ games: [], error: '' });
export function CatalogProvider({ children }: { children: ReactNode }) {
  const [games, setGames] = useState<CatalogGame[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    request<{ games: CatalogGame[] }>('/api/catalog').then(data => {
      if (active) setGames(data.games);
    }).catch(err => { if (active) setError(`分类配置加载失败：${err.message}`); });
    return () => { active = false; };
  }, []);
  return <Context.Provider value={{ games, error }}>{children}</Context.Provider>;
}
export const useCatalog = () => useContext(Context);
