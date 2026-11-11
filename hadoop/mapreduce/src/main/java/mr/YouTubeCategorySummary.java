package mr;

import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.opencsv.CSVParser;
import com.opencsv.CSVParserBuilder;
import com.opencsv.CSVReader;
import com.opencsv.CSVReaderBuilder;
import com.opencsv.exceptions.CsvValidationException;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.FSDataInputStream;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.PathFilter;
import org.apache.hadoop.io.LongWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.InputSplit;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.RecordReader;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.TaskAttemptContext;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;

public final class YouTubeCategorySummary extends Configured implements Tool {
    private static final Pattern REGION_FILE = Pattern.compile("([A-Z]{2})videos\\.csv");

    public static final class KaggleCsvInputFormat
            extends FileInputFormat<LongWritable, Text> {
        @Override
        protected boolean isSplitable(org.apache.hadoop.mapreduce.JobContext context, Path file) {
            return false;
        }

        public static final class RegionalCsvFilter implements PathFilter {
            @Override
            public boolean accept(Path path) {
                return REGION_FILE.matcher(path.getName()).matches();
            }
        }

        @Override
        public RecordReader<LongWritable, Text> createRecordReader(
                InputSplit split, TaskAttemptContext context) {
            return new KaggleCsvRecordReader();
        }
    }

    public static final class KaggleCsvRecordReader extends RecordReader<LongWritable, Text> {
        private CSVReader reader;
        private long rowNumber;
        private long totalLength;
        private final LongWritable key = new LongWritable();
        private final Text value = new Text();

        @Override
        public void initialize(InputSplit split, TaskAttemptContext context) throws IOException {
            org.apache.hadoop.mapreduce.lib.input.FileSplit fileSplit =
                    (org.apache.hadoop.mapreduce.lib.input.FileSplit) split;
            Path path = fileSplit.getPath();
            FSDataInputStream stream = path.getFileSystem(context.getConfiguration()).open(path);
            Reader input = new InputStreamReader(stream, StandardCharsets.UTF_8);
            CSVParser parser = new CSVParserBuilder()
                    .withSeparator(',')
                    .withQuoteChar('"')
                    .withEscapeChar('"')
                    .build();
            reader = new CSVReaderBuilder(input).withCSVParser(parser).build();
            totalLength = split.getLength();
            try {
                reader.readNext();
            } catch (CsvValidationException exception) {
                throw new IOException("Unable to read CSV header from " + path, exception);
            }
        }

        @Override
        public boolean nextKeyValue() throws IOException {
            while (true) {
                String[] fields;
                try {
                    fields = reader.readNext();
                } catch (CsvValidationException exception) {
                    throw new IOException("Invalid CSV record near record " + rowNumber, exception);
                }
                if (fields == null) {
                    return false;
                }
                rowNumber++;
                if (fields.length <= 10) {
                    continue;
                }
                key.set(rowNumber);
                value.set(String.join(
                        "\t", fields[0], fields[4], fields[7], fields[8], fields[10]));
                return true;
            }
        }

        @Override
        public LongWritable getCurrentKey() {
            return key;
        }

        @Override
        public Text getCurrentValue() {
            return value;
        }

        @Override
        public float getProgress() {
            return totalLength == 0 ? 1.0f : Math.min(1.0f, (float) rowNumber / totalLength);
        }

        @Override
        public void close() throws IOException {
            if (reader != null) {
                reader.close();
            }
        }
    }

    public static final class CategoryMapper
            extends Mapper<LongWritable, Text, Text, Text> {
        private String region;

        @Override
        protected void setup(Context context) throws IOException {
            Path input = ((org.apache.hadoop.mapreduce.lib.input.FileSplit)
                    context.getInputSplit()).getPath();
            Matcher matcher = REGION_FILE.matcher(input.getName());
            if (!matcher.matches()) {
                throw new IOException("Expected a regional *videos.csv input, found " + input);
            }
            region = matcher.group(1);
        }

        @Override
        protected void map(LongWritable offset, Text record, Context context)
                throws IOException, InterruptedException {
            String[] fields = record.toString().split("\t", -1);
            if (fields.length != 5 || fields[0].isEmpty() || fields[1].isEmpty()) {
                context.getCounter("youtube", "invalid_records").increment(1);
                return;
            }
            try {
                long views = parseCount(fields[2]);
                long likes = parseCount(fields[3]);
                long comments = parseCount(fields[4]);
                context.write(
                        new Text(region + "\t" + fields[1]),
                        new Text("1," + views + "," + likes + "," + comments));
            } catch (NumberFormatException exception) {
                context.getCounter("youtube", "invalid_records").increment(1);
            }
        }

        private static long parseCount(String value) {
            return value == null || value.isEmpty() ? 0L : Long.parseLong(value);
        }
    }

    public static final class SumReducer extends Reducer<Text, Text, Text, Text> {
        @Override
        protected void reduce(Text key, Iterable<Text> values, Context context)
                throws IOException, InterruptedException {
            long observations = 0L;
            long views = 0L;
            long likes = 0L;
            long comments = 0L;
            for (Text value : values) {
                String[] metrics = value.toString().split(",", -1);
                if (metrics.length != 4) {
                    throw new IOException("Malformed MapReduce metric value: " + value);
                }
                observations += Long.parseLong(metrics[0]);
                views += Long.parseLong(metrics[1]);
                likes += Long.parseLong(metrics[2]);
                comments += Long.parseLong(metrics[3]);
            }
            context.write(
                    key,
                    new Text(observations + "," + views + "," + likes + "," + comments));
        }
    }

    @Override
    public int run(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: YouTubeCategorySummary <hdfs-input-dir> <hdfs-output-dir>");
            return 2;
        }
        Job job = Job.getInstance(getConf(), "youtube-category-summary");
        job.setJarByClass(YouTubeCategorySummary.class);
        job.setInputFormatClass(KaggleCsvInputFormat.class);
        job.setMapperClass(CategoryMapper.class);
        job.setCombinerClass(SumReducer.class);
        job.setReducerClass(SumReducer.class);
        job.setMapOutputKeyClass(Text.class);
        job.setMapOutputValueClass(Text.class);
        job.setOutputKeyClass(Text.class);
        job.setOutputValueClass(Text.class);
        FileInputFormat.addInputPath(job, new Path(args[0]));
        FileInputFormat.setInputPathFilter(job, RegionalCsvFilter.class);
        FileOutputFormat.setOutputPath(job, new Path(args[1]));
        return job.waitForCompletion(true) ? 0 : 1;
    }

    public static void main(String[] args) throws Exception {
        System.exit(ToolRunner.run(new YouTubeCategorySummary(), args));
    }
}
