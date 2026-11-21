import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { CatalogProvider } from './hooks/useCatalog';

createRoot(document.getElementById('root')!).render(<CatalogProvider><App /></CatalogProvider>);
