'use client'
import { usePathname } from 'next/navigation'
import Link from 'next/link'

const groups = [
  ['VISÃO', [['Visão Multiplantas','/multiplantas','▥',true],['Cockpit Executivo','/cockpit','◫']]],
  ['OPERAÇÃO', [['PCP & Aderência','/pcp','◎'],['Produção & OEE','/oee','◉'],['Capacidade','/capacidade','▦'],['Materiais & Supply','/materiais','⬟'],['Logística','/logistica','▰']]],
  ['RESULTADO', [['Finanças & DRE','/financas','▮'],['Diagnóstico','/diagnostico','⌕',true]]],
  ['INTELIGÊNCIA', [['Alavancas de Valor','/alavancas','◆'],['Plano de Ação','/plano-acao','◇'],['Agente de Performance','/agente','✦'],['Relatórios','/relatorios','▤']]],
  ['ADMINISTRAÇÃO', [['Central de Dados','/central-dados','▣'],['Mapeamentos','/mapeamentos','⌘'],['Qualidade dos Dados','/qualidade-dados','✓'],['Meu Plano','/meu-plano','○'],['Ajuda','/ajuda','?']]],
]

export default function Sidebar(){
  const pathname=usePathname()
  return <aside className="sidebar">
    <div className="brand"><div className="brand-bars"><i/><i/><i/></div><div><strong>Industrial<br/>Performance</strong><span>by H2M Consulting</span></div></div>
    <div className="brand-tagline">Da operação ao resultado</div>
    <nav>{groups.map(([label,items])=><section key={label}><h6>{label}</h6>{items.map(([name,href,icon,full])=><Link key={href} className={`nav-item ${pathname===href?'active':''}`} href={href}><span className="nav-icon">{icon}</span><span>{name}</span>{full&&<b>FULL</b>}</Link>)}</section>)}</nav>
    <div className="plan-box"><div><strong>Plano Full</strong><span>Todos os módulos disponíveis para sua operação.</span></div><button>Ver meu plano</button></div>
  </aside>
}
