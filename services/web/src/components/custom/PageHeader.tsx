import React from 'react';

interface PageHeaderProps {
  label?: string;
  title: string;
  description?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ label, title, description }) => {
  return (
    <header className="flex flex-col gap-2 mb-7">
      {label ? (
        <p className="text-[12px] uppercase tracking-[0.12em] font-bold text-sky-500 m-0">{label}</p>
      ) : null}
      <h1 className="m-0 text-[clamp(28px,4vw,36px)] leading-[1.1] font-bold">{title}</h1>
      {description ? <p className="m-0 text-slate-600 max-w-[620px]">{description}</p> : null}
    </header>
  );
};
