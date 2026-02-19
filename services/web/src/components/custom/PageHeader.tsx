import React from 'react';

interface PageHeaderProps {
  label?: string;
  title: string;
  description?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({ label, title, description }) => {
  return (
    <header className="flex flex-col gap-2 mb-7">
      {label ? <p className="text-page-label">{label}</p> : null}
      <h1 className="text-page-title">{title}</h1>
      {description ? <p className="m-0 max-w-[620px] text-muted-foreground">{description}</p> : null}
    </header>
  );
};
