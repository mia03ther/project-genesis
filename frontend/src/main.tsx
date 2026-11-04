import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { ProductApp } from './product/ProductApp';
import './style.css';

const root = document.getElementById('root');
if (root) createRoot(root).render(<StrictMode><ProductApp /></StrictMode>);
