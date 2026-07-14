import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  FormControlLabel,
  Link,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import ArticleIcon from '@mui/icons-material/Article'
import DownloadIcon from '@mui/icons-material/Download'
import ImageIcon from '@mui/icons-material/Image'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import QuizIcon from '@mui/icons-material/Quiz'
import TableChartIcon from '@mui/icons-material/TableChart'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import './App.css'

type FormatResponse = {
  supported_extensions: string[]
}

type LongreadTable = {
  headers: string[]
  rows: string[][]
}

type QuizOption = {
  id: string
  text: string
}

type QuizQuestion = {
  question: string
  options: QuizOption[]
  correct_option_id: string
  explanation?: string
}

type LongreadQuiz = {
  questions: QuizQuestion[]
}

type ParseBlock = {
  index: number
  type: string
  title: string
  content: string
  lead?: string
  paragraphs?: string[]
  summary: string
  key_terms: string[]
  takeaways?: string[]
  hints: string[]
  metadata: Record<string, unknown>
  table?: LongreadTable
  quiz?: LongreadQuiz
  image_path?: string
  media_url?: string
  media_type?: string
}

type ParseResponse = {
  filename: string
  title?: string
  source_file?: string
  metadata?: Record<string, unknown>
  blocks: ParseBlock[]
}

type PipelineResponse = {
  filename: string
  pipeline: ParseResponse
}

const API_BASE = '/api'
const FALLBACK_FORMATS = [
  '.pdf',
  '.pptx',
  '.pptm',
  '.docx',
  '.txt',
  '.mp3',
  '.mp4',
  '.mpeg',
  '.mpga',
  '.m4a',
  '.wav',
  '.webm',
]

async function fetchFormats(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/formats`)
  if (!response.ok) {
    throw new Error('Не удалось получить список форматов')
  }

  const data = (await response.json()) as FormatResponse
  return data.supported_extensions ?? []
}

async function sendFile(file: File): Promise<ParseResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE}/pipeline`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `Request failed with status ${response.status}`)
  }

  const data = (await response.json()) as PipelineResponse
  return data.pipeline
}

async function downloadScormPackage(file: File): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE}/export/scorm`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `SCORM export failed with status ${response.status}`)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const disposition = response.headers.get('content-disposition') || ''
  const filename = parseFilename(disposition) || `${file.name.replace(/\.[^.]+$/, '')}-scorm.zip`
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [formats, setFormats] = useState<string[]>([])
  const [loadingFormats, setLoadingFormats] = useState(true)
  const [loading, setLoading] = useState(false)
  const [exportingScorm, setExportingScorm] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<ParseResponse | null>(null)

  useEffect(() => {
    let active = true

    fetchFormats()
      .then((items) => {
        if (active) {
          setFormats(items)
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Не удалось загрузить форматы')
        }
      })
      .finally(() => {
        if (active) {
          setLoadingFormats(false)
        }
      })

    return () => {
      active = false
    }
  }, [])

  const fileLabel = useMemo(() => {
    if (!file) {
      return 'Файл не выбран'
    }
    return `${file.name} · ${(file.size / 1024).toFixed(1)} KB`
  }, [file])

  const stats = useMemo(() => {
    const metadata = result?.metadata ?? {}
    return {
      blocks: result?.blocks?.length ?? 0,
      text: Number(metadata.text_chunk_count ?? 0),
      tables: Number(metadata.table_count ?? 0),
      images: Number(metadata.image_count ?? 0),
      quizzes: Number(metadata.quiz_count ?? 0),
    }
  }, [result])

  const handleSubmit = async () => {
    if (!file) {
      setError('Сначала выбери файл')
      return
    }

    setLoading(true)
    setError('')

    try {
      const data = await sendFile(file)
      setResult(data)
    } catch (err: unknown) {
      setResult(null)
      setError(err instanceof Error ? err.message : 'Неизвестная ошибка')
    } finally {
      setLoading(false)
    }
  }

  const handleScormExport = async () => {
    if (!file) {
      setError('Сначала выбери файл')
      return
    }

    setExportingScorm(true)
    setError('')

    try {
      await downloadScormPackage(file)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Не удалось собрать SCORM-пакет')
    } finally {
      setExportingScorm(false)
    }
  }

  return (
    <Box className="app-shell">
      <Container maxWidth="xl">
        <Paper elevation={0} className="upload-panel">
          <Stack spacing={2.5}>
            <Box>
              <Typography variant="overline" className="eyebrow">
                LongridMaker
              </Typography>
              <Typography variant="h3" className="title">
                Лекция в формате лонгрида
              </Typography>
              
            </Box>

            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              {loadingFormats ? (
                <Chip label="Загружаю форматы..." />
              ) : (
                formats.map((format) => <Chip key={format} label={format} />)
              )}
            </Stack>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <Button
                variant="contained"
                size="large"
                startIcon={<UploadFileIcon />}
                component="label"
              >
                Выбрать файл
                <input
                  hidden
                  type="file"
                  accept={formats.length > 0 ? formats.join(',') : FALLBACK_FORMATS.join(',')}
                  onChange={(event) => {
                    const nextFile = event.target.files?.[0] ?? null
                    setFile(nextFile)
                    setResult(null)
                    setError('')
                  }}
                />
              </Button>

              <Button
                variant="outlined"
                size="large"
                startIcon={<PlayArrowIcon />}
                onClick={handleSubmit}
                disabled={!file || loading}
              >
                Собрать лонгрид
              </Button>

              <Button
                variant="outlined"
                size="large"
                startIcon={<DownloadIcon />}
                onClick={handleScormExport}
                disabled={!file || exportingScorm}
              >
                {exportingScorm ? 'Сборка SCORM...' : 'Скачать SCORM'}
              </Button>

              <TextField
                label="Выбранный файл"
                value={fileLabel}
                slotProps={{ input: { readOnly: true } }}
                fullWidth
              />
            </Stack>
          </Stack>
        </Paper>

        {error ? (
          <Box className="status-window">
            <Alert severity="error">{error}</Alert>
          </Box>
        ) : null}

        {loading ? (
          <Paper elevation={0} className="status-window">
            <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
              <CircularProgress size={24} />
              <Typography variant="body1">Идет обработка файла...</Typography>
            </Stack>
          </Paper>
        ) : null}

        {result ? (
          <Box className="longread-layout">
            <Paper elevation={0} className="toc-panel">
              <Stack spacing={2}>
                <Box>
                  <Typography variant="overline" className="eyebrow">
                    Оглавление
                  </Typography>
                  <Typography variant="h6">{result.title || result.filename}</Typography>
                </Box>

                <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                  <Chip label={`${stats.blocks} блоков`} size="small" />
                  <Chip label={`${stats.text} разделов`} size="small" />
                  <Chip label={`${stats.tables} таблиц`} size="small" />
                  <Chip label={`${stats.images} изображений`} size="small" />
                  <Chip label={`${stats.quizzes} квиз`} size="small" />
                </Stack>

                <Divider />

                <Stack spacing={1}>
                  {result.blocks.map((block) => (
                    <Link key={block.index} href={`#block-${block.index}`} underline="none" className="toc-link">
                      <BlockIcon type={block.type} />
                      <span>{block.title}</span>
                    </Link>
                  ))}
                </Stack>
              </Stack>
            </Paper>

            <Box component="article" className="article">
              <Paper elevation={0} className="article-header">
                <Typography variant="overline" className="eyebrow">
                  Черновик лонгрида
                </Typography>
                <Typography variant="h2">{result.title || result.filename}</Typography>
                <Typography variant="body1" color="text.secondary">
                  Источник: {result.source_file || result.filename}
                </Typography>
              </Paper>

              {result.blocks.map((block) => (
                <ArticleBlock key={block.index} block={block} />
              ))}
            </Box>
          </Box>
        ) : null}
      </Container>
    </Box>
  )
}

export default App

function ArticleBlock({ block }: { block: ParseBlock }) {
  if (block.type === 'table' && block.table) {
    return <TableBlock block={block} />
  }

  if (block.type === 'image') {
    return <ImageBlock block={block} />
  }

  if (block.type === 'quiz' && block.quiz) {
    return <QuizBlock block={block} />
  }

  const paragraphs = block.paragraphs?.length ? block.paragraphs : [block.content].filter(Boolean)

  return (
    <Paper id={`block-${block.index}`} elevation={0} className="article-section">
      <Stack spacing={2}>
        <Stack spacing={1}>
          <BlockLabel type={block.type} />
          <Typography variant="h4">{block.title}</Typography>
          {block.lead ? (
            <Typography variant="body1" className="lead">
              {block.lead}
            </Typography>
          ) : null}
        </Stack>

        <Stack spacing={1.4}>
          {paragraphs.map((paragraph, index) => (
            <Typography key={`${block.index}-${index}`} variant="body1" className="article-paragraph">
              {paragraph}
            </Typography>
          ))}
        </Stack>

        {block.key_terms?.length ? (
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            {block.key_terms.map((term) => (
              <Chip key={term} label={term} size="small" variant="outlined" />
            ))}
          </Stack>
        ) : null}

        {block.takeaways?.length ? (
          <Box className="takeaways">
            <Typography variant="subtitle2">Главное</Typography>
            <ul>
              {block.takeaways.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Box>
        ) : null}
      </Stack>
    </Paper>
  )
}

function TableBlock({ block }: { block: ParseBlock }) {
  const headers = block.table?.headers ?? []
  const rows = block.table?.rows ?? []

  return (
    <Paper id={`block-${block.index}`} elevation={0} className="article-section media-section">
      <Stack spacing={2}>
        <Stack spacing={1}>
          <BlockLabel type="table" />
          <Typography variant="h4">{block.title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {block.summary}
          </Typography>
        </Stack>

        <TableContainer className="data-table">
          <Table size="small">
            {headers.length ? (
              <TableHead>
                <TableRow>
                  {headers.map((header, index) => (
                    <TableCell key={`${header}-${index}`}>{header || `Колонка ${index + 1}`}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
            ) : null}
            <TableBody>
              {rows.map((row, rowIndex) => (
                <TableRow key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <TableCell key={`${rowIndex}-${cellIndex}`}>{cell}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Stack>
    </Paper>
  )
}

function ImageBlock({ block }: { block: ParseBlock }) {
  const metadataUrl = typeof block.metadata?.media_url === 'string' ? block.metadata.media_url : undefined
  const imageSrc = block.media_url || metadataUrl

  return (
    <Paper id={`block-${block.index}`} elevation={0} className="article-section media-section">
      <Stack spacing={2}>
        <Stack spacing={1}>
          <BlockLabel type="image" />
          <Typography variant="h4">{block.title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {block.summary}
          </Typography>
        </Stack>

        {imageSrc ? (
          <Box
            component="img"
            src={imageSrc}
            alt={block.summary || block.title}
            className="longread-image"
          />
        ) : (
          <Box className="image-placeholder">
            <ImageIcon />
            <Typography variant="body2">Предпросмотр изображения недоступен</Typography>
          </Box>
        )}
      </Stack>
    </Paper>
  )
}

function QuizBlock({ block }: { block: ParseBlock }) {
  const questions = block.quiz?.questions ?? []
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const answeredCount = questions.filter((_, index) => answers[index]).length
  const correctCount = questions.filter(
    (question, index) => answers[index] === question.correct_option_id,
  ).length

  return (
    <Paper id={`block-${block.index}`} elevation={0} className="article-section quiz-section">
      <Stack spacing={2.5}>
        <Stack spacing={1}>
          <BlockLabel type="quiz" />
          <Typography variant="h4">{block.title}</Typography>
          <Typography variant="body1" className="lead">
            {block.lead || block.summary}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Chip label={`${questions.length} вопросов`} size="small" />
            <Chip label={`${correctCount}/${answeredCount || questions.length} верно`} size="small" variant="outlined" />
          </Stack>
        </Stack>

        <Stack spacing={2}>
          {questions.map((question, questionIndex) => {
            const selected = answers[questionIndex]
            const isAnswered = Boolean(selected)
            const isCorrect = selected === question.correct_option_id

            return (
              <Box key={`${block.index}-question-${questionIndex}`} className="quiz-question">
                <Typography variant="subtitle1" className="quiz-question-title">
                  {questionIndex + 1}. {question.question}
                </Typography>
                <RadioGroup
                  value={selected || ''}
                  onChange={(event) => {
                    setAnswers((current) => ({
                      ...current,
                      [questionIndex]: event.target.value,
                    }))
                  }}
                >
                  {question.options.map((option) => {
                    const isSelected = selected === option.id
                    const isRightOption = option.id === question.correct_option_id
                    const stateClass = isAnswered
                      ? isRightOption
                        ? 'is-correct'
                        : isSelected
                          ? 'is-wrong'
                          : ''
                      : ''

                    return (
                      <FormControlLabel
                        key={option.id}
                        value={option.id}
                        control={<Radio size="small" />}
                        label={`${option.id}. ${option.text}`}
                        className={`quiz-option ${stateClass}`}
                      />
                    )
                  })}
                </RadioGroup>

                {isAnswered ? (
                  <Box className={`quiz-feedback ${isCorrect ? 'is-correct' : 'is-wrong'}`}>
                    <Typography variant="subtitle2">
                      {isCorrect ? 'Верно' : 'Нужно повторить'}
                    </Typography>
                    {question.explanation ? (
                      <Typography variant="body2">{question.explanation}</Typography>
                    ) : null}
                  </Box>
                ) : null}
              </Box>
            )
          })}
        </Stack>
      </Stack>
    </Paper>
  )
}

function BlockLabel({ type }: { type: string }) {
  return (
    <Stack direction="row" spacing={1} className="block-label">
      <BlockIcon type={type} />
      <Typography variant="caption">{blockTypeLabel(type)}</Typography>
    </Stack>
  )
}

function BlockIcon({ type }: { type: string }) {
  if (type === 'table') {
    return <TableChartIcon fontSize="small" />
  }
  if (type === 'image') {
    return <ImageIcon fontSize="small" />
  }
  if (type === 'quiz') {
    return <QuizIcon fontSize="small" />
  }
  return <ArticleIcon fontSize="small" />
}

function blockTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    introduction: 'Введение',
    theory: 'Теория',
    examples: 'Пример',
    conclusion: 'Вывод',
    table: 'Таблица',
    image: 'Иллюстрация',
    quiz: 'Мини-квиз',
  }
  return labels[type] || 'Раздел'
}

function parseFilename(contentDisposition: string): string | undefined {
  const utfMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utfMatch?.[1]) {
    return decodeURIComponent(utfMatch[1])
  }

  const match = contentDisposition.match(/filename="?([^";]+)"?/i)
  return match?.[1]
}
